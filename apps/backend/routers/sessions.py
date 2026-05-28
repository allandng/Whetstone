"""Routes for problem-solving sessions.

Stub CRUD endpoints for :class:`models.Session`. Bodies are placeholders
until the persistence and domain logic land.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession

from db import get_session
from events import list_session_events
from models import Session as SessionModel
from schemas import EventRead

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


@router.get("/{session_id}/timeline", response_model=list[EventRead])
async def get_session_timeline(
    session_id: uuid.UUID, db: DBSession = Depends(get_session)
) -> list[EventRead]:
    """Return the session's events in chronological order (FR-SESS-2)."""

    if db.get(SessionModel, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return list_session_events(db, session_id)
