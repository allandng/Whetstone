"""Routes for notebook cells.

CRUD for :class:`models.Cell` plus execution. Running a cell submits it to
Psirver (:class:`services.psirver_client.PsirverClient`) and records a
``cell_run`` / ``cell_result`` pair on the session's event log, which is what
makes the timeline populate from real HTTP activity rather than a CLI seed.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession
from sqlmodel import func, select

from db import get_session
from events import emit_event
from models import Cell, CellType, Session as SessionModel
from schemas import CellCreate, CellRead, CellUpdate
from services.psirver_client import PsirverClient, PsirverUnavailableError

router = APIRouter(prefix="/cells", tags=["cells"])

psirver_client = PsirverClient()

# Psirver job states that mean the job is done (per PsirverClient.poll_job).
_TERMINAL_STATES = {"COMPLETED", "FAILED", "TERMINATED"}

# Bounded polling so a wedged job can't hang the request indefinitely.
_POLL_INTERVAL_SECONDS = 0.2
_MAX_POLLS = 150  # ~30s ceiling


@router.post("", response_model=CellRead)
async def create_cell(
    body: CellCreate, db: DBSession = Depends(get_session)
) -> Cell:
    """Create a new cell in a session, appended to the end by default."""

    if db.get(SessionModel, body.session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    order_index = body.order_index
    if order_index is None:
        order_index = _next_order_index(db, body.session_id)

    cell = Cell(
        session_id=body.session_id,
        cell_type=body.cell_type,
        language=body.language,
        content=body.content,
        order_index=order_index,
    )
    db.add(cell)
    _touch_session(db, body.session_id)
    db.commit()
    db.refresh(cell)
    return cell


@router.put("/{cell_id}", response_model=CellRead)
async def update_cell(
    cell_id: uuid.UUID, body: CellUpdate, db: DBSession = Depends(get_session)
) -> Cell:
    """Update a cell's source or metadata (only provided fields are applied)."""

    cell = db.get(Cell, cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail="Cell not found.")

    if body.content is not None:
        cell.content = body.content
    if body.cell_type is not None:
        cell.cell_type = body.cell_type
    if body.language is not None:
        cell.language = body.language
    if body.order_index is not None:
        cell.order_index = body.order_index

    db.add(cell)
    _touch_session(db, cell.session_id)
    db.commit()
    db.refresh(cell)
    return cell


@router.post("/{cell_id}/run", response_model=CellRead)
async def run_cell(
    cell_id: uuid.UUID, db: DBSession = Depends(get_session)
) -> Cell:
    """Run a cell via Psirver and record the run on the timeline.

    Emits ``cell_run`` (the attempt) then ``cell_result`` (the outcome) so the
    session timeline reflects the execution. If Psirver is unreachable the run
    is recorded with ``status="error"`` and the failure as output rather than
    raising, so a timeline can be seeded over HTTP with only the backend up.
    """

    cell = db.get(Cell, cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail="Cell not found.")
    if cell.cell_type is not CellType.code:
        raise HTTPException(status_code=400, detail="Only code cells can be run.")

    session_id = cell.session_id
    emit_event(
        db,
        session_id=session_id,
        event_type="cell_run",
        payload={"cell_id": str(cell.id), "code": cell.content},
    )

    status, output = await _execute(cell)

    cell.status = status
    cell.last_output = output
    db.add(cell)
    _touch_session(db, session_id)
    emit_event(
        db,
        session_id=session_id,
        event_type="cell_result",
        payload={"cell_id": str(cell.id), "status": status, "output": output},
    )
    db.refresh(cell)
    return cell


@router.delete("/{cell_id}")
async def delete_cell(
    cell_id: uuid.UUID, db: DBSession = Depends(get_session)
) -> dict:
    """Delete a cell."""

    cell = db.get(Cell, cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail="Cell not found.")

    session_id = cell.session_id
    db.delete(cell)
    _touch_session(db, session_id)
    db.commit()
    return {"status": "deleted", "cell_id": str(cell_id)}


# --- Helpers ---------------------------------------------------------------


def _next_order_index(db: DBSession, session_id: uuid.UUID) -> int:
    """Return the order_index that appends a cell after the session's last."""

    current_max = db.exec(
        select(func.max(Cell.order_index)).where(Cell.session_id == session_id)
    ).one()
    return 0 if current_max is None else current_max + 1


def _touch_session(db: DBSession, session_id: uuid.UUID) -> None:
    """Bump the parent session's ``modified_at`` (committed by the caller)."""

    session = db.get(SessionModel, session_id)
    if session is not None:
        session.modified_at = datetime.now(timezone.utc)
        db.add(session)


async def _execute(cell: Cell) -> tuple[str, str]:
    """Submit the cell to Psirver and poll to completion.

    Returns a ``(status, output)`` pair where ``status`` is one of ``ok`` /
    ``error`` / ``terminated`` / ``timeout``. Psirver/transport failures and an
    unsupported language are folded into ``("error", message)`` so the caller
    can still record a result.
    """

    language = cell.language or "python"
    try:
        job_id = await psirver_client.submit_job(language, cell.content)
        for _ in range(_MAX_POLLS):
            job = await psirver_client.poll_job(job_id)
            if job.get("status") in _TERMINAL_STATES:
                return _normalize_result(job)
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        return "timeout", "Execution did not finish within the time limit."
    except ValueError as exc:  # unsupported language
        return "error", str(exc)
    except (PsirverUnavailableError, httpx.HTTPError) as exc:
        return "error", f"Could not reach the execution service: {exc}"


def _normalize_result(job: dict) -> tuple[str, str]:
    """Map a terminal Psirver job into a ``(status, output)`` pair."""

    output = (job.get("stdout") or "") + (job.get("stderr") or "")
    job_status = job.get("status")
    if job_status == "COMPLETED":
        status = "ok" if job.get("exit_code") in (0, None) else "error"
    elif job_status == "TERMINATED":
        status = "terminated"
    else:  # FAILED
        status = "error"
    return status, output
