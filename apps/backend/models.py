"""SQLModel table definitions.

The Whetstone domain model. These tables capture the core entities
described in the SRS:

- :class:`Session`         - a problem-solving session (one assignment).
- :class:`Cell`            - a notebook cell (code or notes) in a session.
- :class:`Spec`            - an imported assignment spec (PDF/text).
- :class:`RequirementItem` - a tracked checklist item parsed from a spec.
- :class:`Event`           - an append-only timeline entry (edit, run,
                             error, AI exchange) used for replay.

:class:`CellRequirementLink` is the association table backing the
many-to-many relationship between cells and requirement items, so a cell
can satisfy several requirements and a requirement can be addressed by
several cells.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CellType(str, Enum):
    """Kind of notebook cell."""

    code = "code"
    notes = "notes"


class SourceType(str, Enum):
    """Origin of an imported spec."""

    pdf = "pdf"
    text = "text"


class RequirementStatus(str, Enum):
    """Progress of a tracked requirement item."""

    not_started = "not_started"
    in_progress = "in_progress"
    done = "done"


class CellRequirementLink(SQLModel, table=True):
    """Association table linking cells to the requirements they address."""

    cell_id: uuid.UUID = Field(foreign_key="cell.id", primary_key=True)
    requirement_id: uuid.UUID = Field(
        foreign_key="requirementitem.id", primary_key=True
    )


class Session(SQLModel, table=True):
    """A single problem-solving session for one assignment."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(default="Untitled session")
    created_at: datetime = Field(default_factory=_utcnow)
    modified_at: datetime = Field(default_factory=_utcnow)
    spec_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="spec.id", index=True
    )

    spec: Optional["Spec"] = Relationship(back_populates="sessions")
    cells: list["Cell"] = Relationship(back_populates="session")
    events: list["Event"] = Relationship(back_populates="session")


class Cell(SQLModel, table=True):
    """A notebook cell belonging to a session."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="session.id", index=True)
    cell_type: CellType = Field(default=CellType.code)
    language: Optional[str] = Field(default=None)
    content: str = Field(default="")
    last_output: Optional[str] = Field(default=None)
    status: str = Field(default="idle")
    order_index: int = Field(default=0)

    session: Optional["Session"] = Relationship(back_populates="cells")
    requirements: list["RequirementItem"] = Relationship(
        back_populates="cells", link_model=CellRequirementLink
    )


class Spec(SQLModel, table=True):
    """An imported assignment specification."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_type: SourceType = Field(default=SourceType.text)
    raw_text: str = Field(default="")

    sessions: list["Session"] = Relationship(back_populates="spec")
    requirements: list["RequirementItem"] = Relationship(
        back_populates="spec"
    )


class RequirementItem(SQLModel, table=True):
    """A single tracked requirement parsed from a spec."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    spec_id: uuid.UUID = Field(foreign_key="spec.id", index=True)
    text: str = Field(default="")
    status: RequirementStatus = Field(default=RequirementStatus.not_started)

    spec: Optional["Spec"] = Relationship(back_populates="requirements")
    cells: list["Cell"] = Relationship(
        back_populates="requirements", link_model=CellRequirementLink
    )


class Event(SQLModel, table=True):
    """An append-only timeline event recording session activity.

    Events are never updated or deleted; they are written once and read
    back in order to replay a session.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="session.id", index=True)
    timestamp: datetime = Field(default_factory=_utcnow, index=True)
    event_type: str = Field(default="note")
    payload: str = Field(default="{}", description="JSON-encoded event data.")

    session: Optional["Session"] = Relationship(back_populates="events")
