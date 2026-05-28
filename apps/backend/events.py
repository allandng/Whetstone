"""Event-log helpers: the append-only session timeline / audit record.

In v1 the Event log is an append-only audit and timeline record, **not** the
source of truth: ``Session`` and ``Cell`` keep their own mutable state. These
helpers centralize the two operations routers need so they don't build
``Event`` rows inline:

- :func:`emit_event`         - append one event (any router can call this).
- :func:`list_session_events` - read a session's events in timeline order.

``event_type`` is a free string; callers pass a stable label (e.g.
``"ai_exchange"``, ``"cell_run"``) and a JSON-serializable ``payload`` dict.
"""

from __future__ import annotations

import json
import uuid

from sqlmodel import Session as DBSession
from sqlmodel import select

from models import Event


def emit_event(
    db: DBSession,
    *,
    session_id: uuid.UUID,
    event_type: str,
    payload: dict | None = None,
) -> Event:
    """Append one event to ``session_id``'s timeline and return it.

    The ``payload`` dict is JSON-encoded into the event's ``payload`` column.
    Commits on the given session so the event is durable as soon as it is
    emitted, matching the append-only audit semantics.
    """

    event = Event(
        session_id=session_id,
        event_type=event_type,
        payload=json.dumps(payload or {}),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_session_events(db: DBSession, session_id: uuid.UUID) -> list[Event]:
    """Return all events for ``session_id`` in chronological order."""

    return list(
        db.exec(
            select(Event)
            .where(Event.session_id == session_id)
            .order_by(Event.timestamp)
        ).all()
    )
