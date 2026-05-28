"""Pydantic response schemas.

Read-side (response) models returned by the API, decoupled from the
SQLModel table definitions in :mod:`models`. Each table model has a
matching ``*Read`` schema here. ``from_attributes`` is enabled so these
can be built directly from ORM instances.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from models import CellType, RequirementStatus, SourceType


class SessionRead(BaseModel):
    """Response schema for a :class:`models.Session`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    modified_at: datetime
    spec_id: Optional[uuid.UUID]


class CellRead(BaseModel):
    """Response schema for a :class:`models.Cell`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    cell_type: CellType
    language: Optional[str]
    content: str
    last_output: Optional[str]
    status: str
    order_index: int


class SpecRead(BaseModel):
    """Response schema for a :class:`models.Spec`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: SourceType
    raw_text: str


class RequirementItemRead(BaseModel):
    """Response schema for a :class:`models.RequirementItem`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    spec_id: uuid.UUID
    text: str
    status: RequirementStatus


# --- Spec import / requirements -------------------------------------------


class SpecImportResponse(BaseModel):
    """Returned immediately from ``POST /specs/import``.

    ``status`` is always ``"extracting"``: the Spec row is persisted before the
    response, while requirement extraction runs in a background task.
    """

    spec_id: uuid.UUID
    status: str


class RequirementUpdate(BaseModel):
    """Request body for ``PATCH /requirements/{id}`` (manual edit).

    Both fields are optional; only the ones provided are applied.
    """

    status: Optional[RequirementStatus] = None
    text: Optional[str] = None


class AttachSpecRequest(BaseModel):
    """Request body for ``POST /sessions/{id}/spec``."""

    spec_id: uuid.UUID


# --- Session timeline ------------------------------------------------------


class TimelineEvent(BaseModel):
    """An :class:`models.Event` with its payload decoded from JSON."""

    id: uuid.UUID
    session_id: uuid.UUID
    timestamp: datetime
    event_type: str
    payload: dict[str, Any]


class SessionTimeline(BaseModel):
    """Response schema for ``GET /sessions/{id}/timeline``.

    ``events`` is the flat list ordered by timestamp (what the UI renders and
    replays); ``groups`` buckets the same events by ``event_type`` (CELL_RUN,
    CELL_RESULT, AI_EXCHANGE, MODE_SWITCH, VOICE_NOTE, ...).
    """

    session_id: uuid.UUID
    events: list[TimelineEvent]
    groups: dict[str, list[TimelineEvent]]
