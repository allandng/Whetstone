"""Routes for assignment specs and requirement tracking.

Importing a :class:`models.Spec` (PDF or text) and managing the
:class:`models.RequirementItem` checklist parsed from it (SRS §4.1):

- ``POST /specs/import``             - store a spec, kick off extraction.
- ``GET  /specs/{id}/requirements``  - list the parsed checklist.
- ``PATCH /requirements/{id}``       - manual edit of one checklist item.

Extraction runs as a FastAPI ``BackgroundTask`` so ``/specs/import`` returns
immediately with ``status="extracting"``; the checklist appears once the LLM
reply has been parsed and written.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlmodel import Session as DBSession
from sqlmodel import select

from db import get_session, session_scope
from events import emit_event
from models import (
    RequirementItem,
    RequirementStatus,
    Session as SessionModel,
    SourceType,
    Spec,
)
from schemas import RequirementItemRead, RequirementUpdate, SpecImportResponse
from services.llm_client import LLMClient, LLMUnavailableError
from services.spec_parser import (
    build_extraction_messages,
    extract_pdf_text,
    parse_requirements,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["spec"])

llm_client = LLMClient()


@router.post("/specs/import", response_model=SpecImportResponse)
async def import_spec(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(default=None),
    raw_text: str | None = Form(default=None),
    db: DBSession = Depends(get_session),
) -> SpecImportResponse:
    """Import a spec (PDF/text) and extract requirements in the background."""

    source_type, text = await _resolve_source(file, raw_text)

    spec = Spec(source_type=source_type, raw_text=text)
    db.add(spec)
    db.commit()
    db.refresh(spec)

    background_tasks.add_task(_extract_requirements, spec.id)
    return SpecImportResponse(spec_id=spec.id, status="extracting")


@router.get("/specs/{spec_id}/requirements", response_model=list[RequirementItemRead])
async def list_requirements(
    spec_id: uuid.UUID, db: DBSession = Depends(get_session)
) -> list[RequirementItem]:
    """List the requirement items extracted from a spec."""

    if db.get(Spec, spec_id) is None:
        raise HTTPException(status_code=404, detail="Spec not found.")
    return list(
        db.exec(
            select(RequirementItem).where(RequirementItem.spec_id == spec_id)
        ).all()
    )


@router.patch("/requirements/{requirement_id}", response_model=RequirementItemRead)
async def update_requirement(
    requirement_id: uuid.UUID,
    body: RequirementUpdate,
    db: DBSession = Depends(get_session),
) -> RequirementItem:
    """Update a requirement item's status and/or text (manual edit)."""

    item = db.get(RequirementItem, requirement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Requirement not found.")

    old_status = item.status
    if body.status is not None:
        item.status = body.status
    if body.text is not None:
        item.text = body.text

    db.add(item)
    db.commit()
    db.refresh(item)

    if body.status is not None and body.status != old_status:
        _record_status_change(db, item, old_status)

    return item


def _record_status_change(
    db: DBSession, item: RequirementItem, old_status: RequirementStatus
) -> None:
    """Append a ``requirement_status`` event so check-offs land on the timeline.

    Requirements belong to a spec, and a spec may back several sessions, so the
    event is appended to every session that references this requirement's spec.
    This is what lets timeline replay reconstruct requirement check-offs as they
    stood at a past point (the PATCH route is the only place status changes).
    """

    sessions = db.exec(
        select(SessionModel).where(SessionModel.spec_id == item.spec_id)
    ).all()
    for session in sessions:
        emit_event(
            db,
            session_id=session.id,
            event_type="requirement_status",
            payload={
                "requirement_id": str(item.id),
                "text": item.text,
                "from": old_status.value,
                "to": item.status.value,
            },
        )


# --- Helpers ---------------------------------------------------------------


async def _resolve_source(
    file: UploadFile | None, raw_text: str | None
) -> tuple[SourceType, str]:
    """Resolve the request into a ``(source_type, raw_text)`` pair.

    A file takes precedence over ``raw_text``; PDFs are detected by extension
    or content type and run through ``pdfplumber``, anything else is decoded as
    UTF-8 text. Raises 400 if neither a file nor non-empty text is supplied.
    """

    if file is not None:
        data = await file.read()
        name = (file.filename or "").lower()
        content_type = (file.content_type or "").lower()
        if name.endswith(".pdf") or "pdf" in content_type:
            return SourceType.pdf, extract_pdf_text(data)
        return SourceType.text, data.decode("utf-8", errors="replace")

    if raw_text is not None and raw_text.strip():
        return SourceType.text, raw_text

    raise HTTPException(
        status_code=400, detail="Provide a file or non-empty raw_text."
    )


async def _extract_requirements(spec_id: uuid.UUID) -> None:
    """Background task: ask the LLM for requirements and persist them.

    Runs after the ``/specs/import`` response is sent, so it uses its own
    session scope and surfaces failures via the log rather than to the client.
    A dead llama-server leaves the spec with an empty checklist rather than
    raising into the background runner.
    """

    with session_scope() as db:
        spec = db.get(Spec, spec_id)
        if spec is None:
            logger.warning("Spec %s vanished before extraction.", spec_id)
            return
        raw_text = spec.raw_text

    if not raw_text.strip():
        logger.warning("Spec %s has no text to extract from.", spec_id)
        return

    messages = build_extraction_messages(raw_text)
    try:
        chunks = [
            chunk
            async for chunk in llm_client.ask(
                messages, stream=False, thinking=False
            )
        ]
    except LLMUnavailableError as exc:
        logger.error("Requirement extraction failed for spec %s: %s", spec_id, exc)
        return

    requirements = parse_requirements("".join(chunks))
    if not requirements:
        logger.warning("No requirements parsed for spec %s.", spec_id)
        return

    with session_scope() as db:
        for text in requirements:
            db.add(
                RequirementItem(
                    spec_id=spec_id,
                    text=text,
                    status=RequirementStatus.not_started,
                )
            )
        db.commit()
    logger.info("Extracted %d requirements for spec %s.", len(requirements), spec_id)
