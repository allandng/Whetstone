"""Pydantic response schemas.

Read-side (response) models returned by the API, decoupled from the
SQLModel table definitions in :mod:`models`. Each table model has a
matching ``*Read`` schema here. ``from_attributes`` is enabled so these
can be built directly from ORM instances.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

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


class EventRead(BaseModel):
    """Response schema for a :class:`models.Event`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    timestamp: datetime
    event_type: str
    payload: str
