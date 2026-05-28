"""Routes for the AI tutor / co-pilot (Direct mode).

Bridges the frontend to the local LLM (:class:`services.llm_client.LLMClient`)
for the Direct-mode co-pilot features described in SRS §4.3:

- ``POST /ai/explain-error`` — plain-language explanation of a cell error.
- ``POST /ai/ask``           — free-form question, streamed back as SSE.
- ``POST /ai/complexity``    — advisory time/space complexity analysis.

Every request is grounded in the session's context (active requirements,
the referenced cell and its last output, and recent AI exchanges), and the
system prompt carries the academic-integrity rule from FR-AI-6.
"""

from __future__ import annotations

import json
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import select

from db import get_session, session_scope
from events import emit_event
from models import Cell, Event, RequirementItem, Session as SessionModel
from services.llm_client import LLMClient, LLMUnavailableError

router = APIRouter(prefix="/ai", tags=["ai"])

llm_client = LLMClient()

# Event-log type for an AI exchange; the timeline (FR-SESS-1) and the
# "recent exchanges" context below both key off this.
_AI_EVENT_TYPE = "ai_exchange"

# FR-AI-6: a reply containing a complete solution must be unmistakably marked.
_FULL_SOLUTION_PREFIX = (
    "[FULL SOLUTION — academic integrity note: this writes the answer for you]"
)

# FR-AI-4: complexity analysis is the model's reasoning to be verified, not an
# authority. Appended server-side so the framing is guaranteed regardless of
# what a small model emits.
_VERIFY_LINE = "This is the model's reasoning — verify it yourself."

# Soft caps so a large cell, output, or history can't blow up the prompt for a
# small local model.
_MAX_CELL_CHARS = 4000
_MAX_OUTPUT_CHARS = 2000
_MAX_EXCHANGE_CHARS = 600


# --- Request models --------------------------------------------------------


class ExplainErrorRequest(BaseModel):
    cell_id: uuid.UUID
    error_text: str = Field(min_length=1)


class AskRequest(BaseModel):
    session_id: uuid.UUID
    cell_id: Optional[uuid.UUID] = None
    question: str = Field(min_length=1)
    mode: Literal["direct", "socratic"] = "direct"


class ComplexityRequest(BaseModel):
    cell_id: uuid.UUID


# --- Response models -------------------------------------------------------


class ExplainErrorResponse(BaseModel):
    explanation: str


class ComplexityResponse(BaseModel):
    analysis: str


# --- Endpoints -------------------------------------------------------------


@router.post("/explain-error", response_model=ExplainErrorResponse)
async def explain_error(
    body: ExplainErrorRequest, db: DBSession = Depends(get_session)
) -> ExplainErrorResponse:
    """Explain a cell's error in plain language (FR-AI-2)."""

    cell = _require_cell(db, body.cell_id)
    context = _assemble_context(db, cell.session_id, cell)
    user = (
        "The referenced code cell produced the error below. Explain in plain "
        "language what it means and the most likely cause, and suggest how to "
        "investigate it. Do not just rewrite the code for me.\n\n"
        f"Error output:\n{body.error_text}"
    )
    messages = _messages(context, user)
    explanation = await _collect(messages, thinking=False)
    _record_exchange(
        session_id=cell.session_id,
        kind="explain_error",
        mode="direct",
        question=body.error_text,
        response=explanation,
        cell_id=cell.id,
    )
    return ExplainErrorResponse(explanation=explanation)


@router.post("/ask")
async def ask(body: AskRequest, db: DBSession = Depends(get_session)):
    """Answer a free-form question, streamed as SSE (FR-AI-1)."""

    if body.mode == "socratic":
        raise HTTPException(
            status_code=501, detail="Socratic mode is not implemented yet."
        )

    session = db.get(SessionModel, body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    cell = _require_cell(db, body.cell_id) if body.cell_id else None

    context = _assemble_context(db, body.session_id, cell)
    messages = _messages(context, body.question)

    async def event_stream():
        collected: list[str] = []
        try:
            async for chunk in llm_client.ask(messages, stream=True, thinking=False):
                collected.append(chunk)
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
        except LLMUnavailableError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return
        _record_exchange(
            session_id=body.session_id,
            kind="ask",
            mode="direct",
            question=body.question,
            response="".join(collected),
            cell_id=body.cell_id,
        )
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/transcribe")
async def transcribe() -> dict:
    """Transcribe uploaded audio to text via whisper-server. Stub.

    Placeholder for the voice-input feature (SRS §4.5); not part of the
    Direct-mode co-pilot implemented here.
    """

    return {}


@router.post("/complexity", response_model=ComplexityResponse)
async def complexity(
    body: ComplexityRequest, db: DBSession = Depends(get_session)
) -> ComplexityResponse:
    """Analyze the time/space complexity of a cell, as advisory (FR-AI-4)."""

    cell = _require_cell(db, body.cell_id)
    context = _assemble_context(db, cell.session_id, cell)
    user = (
        "Analyze the time and space complexity of the referenced code cell. "
        "Give Big-O bounds for both time and space and justify them step by "
        "step. This is advisory reasoning for the student to check, not an "
        "authoritative result."
    )
    messages = _messages(context, user)
    analysis = await _collect(messages, thinking=True)
    if _VERIFY_LINE not in analysis:
        analysis = f"{analysis.rstrip()}\n\n{_VERIFY_LINE}"
    _record_exchange(
        session_id=cell.session_id,
        kind="complexity",
        mode="direct",
        question="complexity analysis",
        response=analysis,
        cell_id=cell.id,
    )
    return ComplexityResponse(analysis=analysis)


# --- Helpers ---------------------------------------------------------------


def _require_cell(db: DBSession, cell_id: uuid.UUID) -> Cell:
    cell = db.get(Cell, cell_id)
    if cell is None:
        raise HTTPException(status_code=404, detail="Cell not found.")
    return cell


def _system_prompt(context: str) -> str:
    return (
        "You are Whetstone's local AI co-pilot, operating in DIRECT mode for a "
        "computer-science student working through an assignment on their own "
        "machine. Answer accurately and concisely, and show the reasoning "
        "behind your answer so the student can verify it rather than taking it "
        "on faith.\n\n"
        "ACADEMIC INTEGRITY RULE: If your reply contains a complete, "
        "copy-pasteable code solution to the student's task, you MUST begin the "
        "reply with this exact line, on its own:\n"
        f"{_FULL_SOLUTION_PREFIX}\n"
        "If you are giving a hint, a partial snippet, or conceptual guidance "
        "rather than the full answer, do NOT include that line.\n\n"
        "--- SESSION CONTEXT ---\n"
        f"{context}"
    )


def _messages(context: str, user: str) -> list[dict]:
    return [
        {"role": "system", "content": _system_prompt(context)},
        {"role": "user", "content": user},
    ]


def _assemble_context(
    db: DBSession, session_id: uuid.UUID, cell: Optional[Cell]
) -> str:
    """Build the grounding context block for an AI request (item 3)."""

    parts: list[str] = []

    session = db.get(SessionModel, session_id)
    if session is not None and session.spec_id is not None:
        requirements = db.exec(
            select(RequirementItem).where(
                RequirementItem.spec_id == session.spec_id
            )
        ).all()
        if requirements:
            lines = [
                f"- [{req.status.value}] {req.text}" for req in requirements
            ]
            parts.append(
                "Active requirement items for this session:\n"
                + "\n".join(lines)
            )

    if cell is not None:
        parts.append(
            f"Referenced cell (type={cell.cell_type.value}, "
            f"language={cell.language or 'n/a'}):\n"
            f"```\n{_truncate(cell.content, _MAX_CELL_CHARS)}\n```"
        )
        if cell.last_output:
            parts.append(
                "Cell's last output (stdout/stderr):\n"
                f"```\n{_truncate(cell.last_output, _MAX_OUTPUT_CHARS)}\n```"
            )

    exchanges = _recent_exchanges(db, session_id)
    if exchanges:
        parts.append(
            "Recent AI exchanges in this session (oldest first):\n"
            + "\n\n".join(exchanges)
        )

    if not parts:
        return "No additional session context is available."
    return "\n\n".join(parts)


def _recent_exchanges(db: DBSession, session_id: uuid.UUID) -> list[str]:
    events = db.exec(
        select(Event)
        .where(
            Event.session_id == session_id,
            Event.event_type == _AI_EVENT_TYPE,
        )
        .order_by(Event.timestamp.desc())
        .limit(4)
    ).all()
    rendered: list[str] = []
    for event in reversed(events):  # chronological, most recent last
        try:
            data = json.loads(event.payload)
        except json.JSONDecodeError:
            continue
        question = _truncate(data.get("question", ""), _MAX_EXCHANGE_CHARS)
        response = _truncate(data.get("response", ""), _MAX_EXCHANGE_CHARS)
        rendered.append(f"Student: {question}\nTutor: {response}")
    return rendered


def _record_exchange(
    *,
    session_id: uuid.UUID,
    kind: str,
    mode: str,
    question: str,
    response: str,
    cell_id: Optional[uuid.UUID],
) -> None:
    """Append the exchange to the event log (FR-SESS-1)."""

    payload = {
        "kind": kind,
        "mode": mode,
        "question": question,
        "response": response,
        "cell_id": str(cell_id) if cell_id else None,
    }
    # A fresh session (not the request's): for the streaming /ask endpoint
    # this runs after the response body has already been sent.
    with session_scope() as db:
        emit_event(
            db,
            session_id=session_id,
            event_type=_AI_EVENT_TYPE,
            payload=payload,
        )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…[truncated]"


async def _collect(messages: list[dict], thinking: bool) -> str:
    """Consume the non-streaming generator into one string, mapping a dead
    llama-server to a 503 so the caller sees a clear failure (not silence)."""

    try:
        chunks = [
            chunk
            async for chunk in llm_client.ask(
                messages, stream=False, thinking=thinking
            )
        ]
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return "".join(chunks)
