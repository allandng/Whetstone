"""FastAPI application factory for the Whetstone backend.

Builds the app, wires CORS for the Tauri frontend, initializes the
database on startup, and mounts the feature routers (sessions, cells,
ai, spec, practice). Run locally with::

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
from routers import ai, cells, practice, sessions, spec

logger = logging.getLogger("whetstone")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup; tear down on shutdown."""

    create_db_and_tables()
    practice.seed_builtin_problems()
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

    @app.middleware("http")
    async def _limit_body_size(request: Request, call_next):
        """Reject oversized request bodies up front by Content-Length.

        Bounds the spec-import PDF and the transcription audio so a single large
        upload can't exhaust memory before a handler runs. Chunked requests with
        no Content-Length fall through to the handlers, which read defensively.
        """

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > settings.max_upload_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large."},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid Content-Length."}
                )
        return await call_next(request)

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
    app.include_router(practice.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        """Liveness probe."""

        return {"status": "ok"}

    return app


app = create_app()
