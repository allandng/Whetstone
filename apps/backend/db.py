"""Database engine and session management.

Creates the SQLModel/SQLAlchemy engine pointed at the configured SQLite
database and exposes a session factory. ``get_session`` is a FastAPI
dependency that yields a short-lived session per request.

This module owns the engine; routers and services should depend on
``get_session`` rather than constructing sessions directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from config import get_settings

_settings = get_settings()

# ``check_same_thread`` is disabled because FastAPI may use the engine
# across threads; SQLModel/SQLAlchemy manages session lifetimes per call.
engine = create_engine(
    _settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Enable WAL journaling (and FK enforcement) on every connection.

    WAL lets readers and a writer proceed concurrently, which matters for
    a desktop app whose UI reads while a background task writes. SQLite
    applies ``journal_mode`` per connection, so this must run on connect
    rather than once at startup.
    """

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_db_and_tables() -> None:
    """Create all tables registered on the SQLModel metadata.

    Imports :mod:`models` so the table classes register their metadata
    before ``create_all`` runs. Once Alembic migrations are in use this
    becomes a convenience for tests and first-run bootstrapping.
    """

    import models  # noqa: F401  (ensure models are registered)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""

    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a session for work that outlives a single request.

    The ``get_session`` dependency is torn down when its request ends, which
    is the wrong lifetime for writes performed while a streaming response is
    still being produced (e.g. appending an AI exchange to the event log
    once the stream finishes). This gives such code a sanctioned session
    rather than reaching for the engine directly.
    """

    with Session(engine) as session:
        yield session
