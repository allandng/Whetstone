"""HTTP client for Psirver, the C++ code-execution backend.

Psirver runs over loopback and models each execution as an async job:
a script is submitted, then polled for status and captured
stdout/stderr, and may be terminated early. This module wraps those
endpoints behind a small typed client.

Stub: method bodies are not implemented yet.
"""

from __future__ import annotations

import httpx

from config import get_settings


class PsirverClient:
    """Thin async HTTP client around the Psirver job API."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or get_settings().psirver_base_url

    async def submit(self, language: str, source: str) -> str:
        """Submit a script for execution; return a job id.

        Stub.
        """

        raise NotImplementedError

    async def poll(self, job_id: str) -> dict:
        """Return the current status and captured output for a job.

        Stub.
        """

        raise NotImplementedError

    async def terminate(self, job_id: str) -> None:
        """Request termination of a running job.

        Stub.
        """

        raise NotImplementedError

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url)
