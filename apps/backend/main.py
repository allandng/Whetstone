"""FastAPI application factory for the Whetstone backend.

Builds the app, wires CORS for the Tauri frontend, initializes the
database on startup, and mounts the feature routers (sessions, cells,
ai, spec). Run locally with::

    uvicorn main:app --reload

from within ``apps/backend``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from db import init_db
from routers import ai, cells, sessions, spec


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup; tear down on shutdown."""

    init_db()
    yield


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""

    get_settings()  # validate configuration early

    app = FastAPI(title="Whetstone Backend", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(sessions.router)
    app.include_router(cells.router)
    app.include_router(ai.router)
    app.include_router(spec.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        """Liveness probe."""

        return {"status": "ok"}

    return app


app = create_app()
