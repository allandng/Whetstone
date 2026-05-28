"""Routes for problem-solving sessions.

Stub CRUD endpoints for :class:`models.Session`. Bodies are placeholders
until the persistence and domain logic land.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session as DBSession

from db import get_session

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
