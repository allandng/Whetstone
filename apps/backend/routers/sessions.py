"""Routes for problem-solving sessions.

Stub CRUD endpoints for :class:`models.Session`. Bodies are placeholders
until the persistence and domain logic land.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession

from db import get_session
from events import list_session_events
from models import Event, Session as SessionModel, Spec
from schemas import (
    AttachSpecRequest,
    SessionRead,
    SessionTimeline,
    TimelineEvent,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(db: DBSession = Depends(get_session)) -> list[dict]:
    """List all sessions. Stub."""

    return []


@router.post("")
async def create_session(db: DBSession = Depends(get_session)) -> dict:
    """Create a new session. Stub."""

    return {}


@router.get("/{session_id}")
async def get_session_detail(
    session_id: int, db: DBSession = Depends(get_session)
) -> dict:
    """Fetch a single session by id. Stub."""

    return {}


@router.delete("/{session_id}")
async def delete_session(
    session_id: int, db: DBSession = Depends(get_session)
) -> dict:
    """Delete a session by id. Stub."""

    return {}


@router.post("/{session_id}/spec", response_model=SessionRead)
async def attach_spec(
    session_id: uuid.UUID,
    body: AttachSpecRequest,
    db: DBSession = Depends(get_session),
) -> SessionModel:
    """Attach an imported spec to a session (FR-SPEC-3)."""

    session = db.get(SessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if db.get(Spec, body.spec_id) is None:
        raise HTTPException(status_code=404, detail="Spec not found.")

    session.spec_id = body.spec_id
    session.modified_at = datetime.now(timezone.utc)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/{session_id}/timeline", response_model=SessionTimeline)
async def get_session_timeline(
    session_id: uuid.UUID, db: DBSession = Depends(get_session)
) -> SessionTimeline:
    """Return the session's events, ordered and grouped by type (FR-SESS-2).

    Events are returned both as a flat list ordered by timestamp (for the
    timeline/replay view) and bucketed by ``event_type`` (CELL_RUN,
    CELL_RESULT, AI_EXCHANGE, MODE_SWITCH, VOICE_NOTE, ...). Each payload is
    decoded from its stored JSON string.
    """

    if db.get(SessionModel, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    rows = list_session_events(db, session_id)
    events = [_to_timeline_event(event) for event in rows]
    groups: dict[str, list[TimelineEvent]] = {}
    for event in events:
        groups.setdefault(event.event_type, []).append(event)

    return SessionTimeline(session_id=session_id, events=events, groups=groups)


def _to_timeline_event(event: Event) -> TimelineEvent:
    """Build a :class:`TimelineEvent`, decoding the JSON payload string."""

    try:
        payload = json.loads(event.payload)
    except (json.JSONDecodeError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return TimelineEvent(
        id=event.id,
        session_id=event.session_id,
        timestamp=event.timestamp,
        event_type=event.event_type,
        payload=payload,
    )
