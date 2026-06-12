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

from models import (
    CellType,
    ProblemDifficulty,
    ProblemSource,
    ProblemStatus,
    RequirementStatus,
    SourceType,
)


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


# --- Session / cell write models ------------------------------------------


class SessionCreate(BaseModel):
    """Request body for ``POST /sessions``. All fields optional."""

    title: str = "Untitled session"
    spec_id: Optional[uuid.UUID] = None


class CellCreate(BaseModel):
    """Request body for ``POST /cells``.

    ``order_index`` is optional; when omitted the cell is appended to the end
    of its session.
    """

    session_id: uuid.UUID
    cell_type: CellType = CellType.code
    language: Optional[str] = None
    content: str = ""
    order_index: Optional[int] = None


class CellUpdate(BaseModel):
    """Request body for ``PUT /cells/{id}`` (source / metadata edit).

    Only the provided fields are applied. ``last_output`` and ``status`` are
    owned by execution (``POST /cells/{id}/run``) and are not editable here.
    """

    content: Optional[str] = None
    cell_type: Optional[CellType] = None
    language: Optional[str] = None
    order_index: Optional[int] = None


# --- Practice: problems and course ------------------------------------------


class ProblemExample(BaseModel):
    """One worked example in a practice problem statement."""

    input: str = ""
    output: str = ""
    explanation: str = ""


class ProblemRead(BaseModel):
    """Response schema for a :class:`models.Problem`.

    ``examples`` and ``hints`` are decoded from their JSON-string columns by
    the router (this is not built via ``from_attributes``).
    """

    id: uuid.UUID
    slug: str
    title: str
    pattern: str
    pattern_label: str
    difficulty: ProblemDifficulty
    prompt: str
    examples: list[ProblemExample]
    hints: list[str]
    starter_code: str
    language: str
    source: ProblemSource
    parent_problem_id: Optional[uuid.UUID]
    status: ProblemStatus
    created_at: datetime


class ProblemUpdate(BaseModel):
    """Request body for ``PATCH /practice/problems/{id}`` (progress only)."""

    status: ProblemStatus


class GenerateSimilarRequest(BaseModel):
    """Request body for ``POST /practice/problems/{id}/similar``.

    Both fields are optional context for the generator: the user's own note
    about what they struggled with, and their attempted code.
    """

    note: Optional[str] = None
    code: Optional[str] = None


class PracticeStartResponse(BaseModel):
    """Returned by the start-practice routes: the workspace session to open."""

    session_id: uuid.UUID
    spec_id: uuid.UUID


class LessonExercise(BaseModel):
    """The hands-on exercise attached to a course lesson."""

    description: str
    starter_code: str
    language: str = "python"


class LessonRead(BaseModel):
    """One beginner-course lesson, merged with the user's progress."""

    id: str
    title: str
    summary: str
    body: str
    exercise: LessonExercise
    completed: bool


class LessonProgressUpdate(BaseModel):
    """Request body for ``PATCH /practice/course/{lesson_id}``."""

    completed: bool


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
    CELL_RESULT, AI_EXCHANGE, MODE_SWITCH, VOICE_NOTE, REQUIREMENT_STATUS, ...).
    ``requirements`` is the session's current requirement checklist (empty if no
    spec is attached); replay pairs it with ``requirement_status`` events to show
    each item's check-off state at a past point.
    """

    session_id: uuid.UUID
    events: list[TimelineEvent]
    groups: dict[str, list[TimelineEvent]]
    requirements: list[RequirementItemRead]
