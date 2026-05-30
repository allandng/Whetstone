"""FastAPI application factory for the Whetstone backend.

Builds the app, wires CORS for the Tauri frontend, initializes the
database on startup, and mounts the feature routers (sessions, cells,
ai, spec). Run locally with::

    uvicorn main:app --reload

from within ``apps/backend``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from db import create_db_and_tables
from routers import ai, cells, sessions, spec

logger = logging.getLogger("whetstone")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup; tear down on shutdown."""

    create_db_and_tables()
    yield


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""

    settings = get_settings()  # validate configuration early

    app = FastAPI(title="Whetstone Backend", version="1.0.0", lifespan=lifespan)

    # Credentialed access is restricted to the Tauri frontend's origins
    # (configurable via WHETSTONE_CORS_ALLOWED_ORIGINS). A wildcard origin is
    # both invalid alongside credentials and an exposure for a loopback API.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Return a clean JSON error for any unhandled exception.

        Intentional ``HTTPException``s keep FastAPI's own handlers; this is the
        catch-all that turns an unexpected error into a structured ``{"detail":
        ...}`` body (the shape clients already parse) instead of leaking a stack
        trace. The full traceback is logged server-side for debugging.
        """

        logger.exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500, content={"detail": "Internal Server Error"}
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
