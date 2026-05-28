"""Database engine and session management.

Creates the SQLModel/SQLAlchemy engine pointed at the configured SQLite
database and exposes a session factory. ``get_session`` is a FastAPI
dependency that yields a short-lived session per request.

This module owns the engine; routers and services should depend on
``get_session`` rather than constructing sessions directly.
"""

from __future__ import annotations

from collections.abc import Iterator

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


def init_db() -> None:
    """Create all tables registered on the SQLModel metadata.

    Stub: relies on the table models being imported so their metadata is
    registered before ``create_all`` runs. Migrations are out of scope
    for the skeleton.
    """

    import models  # noqa: F401  (ensure models are registered)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""

    with Session(engine) as session:
        yield session
