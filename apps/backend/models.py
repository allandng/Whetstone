"""SQLModel table definitions.

Stub schema for the Whetstone domain model. These tables capture the
core entities described in the SRS:

- :class:`Session`        - a problem-solving session (one assignment).
- :class:`Cell`           - a notebook cell (code or prose) in a session.
- :class:`Spec`           - an imported assignment spec (PDF/text).
- :class:`RequirementItem`- a tracked checklist item parsed from a spec.
- :class:`Event`          - an entry in the session timeline (edit, run,
                            error, AI exchange) used for replay.

Fields are intentionally minimal; relationships and indexes will be
fleshed out as features land.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(SQLModel, table=True):
    """A single problem-solving session for one assignment."""

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(default="Untitled session")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Cell(SQLModel, table=True):
    """A notebook cell belonging to a session."""

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    kind: str = Field(default="code", description="'code' or 'markdown'.")
    language: str = Field(default="python", description="'python' or 'cpp'.")
    source: str = Field(default="")
    position: int = Field(default=0, description="Ordering within session.")
    created_at: datetime = Field(default_factory=_utcnow)


class Spec(SQLModel, table=True):
    """An imported assignment specification."""

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    title: str = Field(default="Untitled spec")
    raw_text: str = Field(default="")
    source_path: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)


class RequirementItem(SQLModel, table=True):
    """A single tracked requirement parsed from a spec."""

    id: Optional[int] = Field(default=None, primary_key=True)
    spec_id: int = Field(foreign_key="spec.id", index=True)
    text: str = Field(default="")
    done: bool = Field(default=False)
    position: int = Field(default=0)


class Event(SQLModel, table=True):
    """A timeline event recording something that happened in a session."""

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id", index=True)
    kind: str = Field(
        default="note",
        description="e.g. 'edit', 'run', 'error', 'ai_exchange'.",
    )
    payload: str = Field(default="{}", description="JSON-encoded event data.")
    created_at: datetime = Field(default_factory=_utcnow)
