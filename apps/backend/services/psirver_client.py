"""HTTP client for Psirver, the C++ code-execution backend.

Psirver runs over loopback and models each execution as an async job:
a script is uploaded, run (which returns a job id immediately, without
blocking), then polled for status and captured stdout/stderr, and may
be terminated early. This module wraps those endpoints behind a small
typed client.
"""

from __future__ import annotations

import httpx

from config import get_settings

# Map caller-facing language names to (Psirver `lang` token, upload filename).
# The filename extension is cosmetic for Python but conventional for C++.
_LANGUAGES = {
    "python": ("python", "script.py"),
    "py": ("python", "script.py"),
    "python3": ("python", "script.py"),
    "cpp": ("cpp", "script.cpp"),
    "c++": ("cpp", "script.cpp"),
    "cxx": ("cpp", "script.cpp"),
}


class PsirverClient:
    """Thin async HTTP client around the Psirver job API."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or get_settings().psirver_base_url

    async def submit_job(self, language: str, source: str) -> str:
        """Upload `source` and start it asynchronously; return the job id.

        Uploads the script (``POST /scripts/upload``) and then kicks off a
        non-blocking run (``POST /scripts/{id}/run``), which replies 202
        Accepted with the job id. Use :meth:`poll_job` to await completion.
        """

        try:
            lang, filename = _LANGUAGES[language.strip().lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported language: {language!r}") from exc

        async with httpx.AsyncClient(base_url=self._base_url) as client:
            upload = await client.post(
                "/scripts/upload",
                files={
                    "file": (
                        filename,
                        source.encode("utf-8"),
                        "application/octet-stream",
                    )
                },
            )
            upload.raise_for_status()
            script_id = int(upload.text.strip())

            run = await client.post(
                f"/scripts/{script_id}/run",
                data={"lang": lang, "args": ""},
            )
            run.raise_for_status()
            return str(run.json()["job_id"])

    async def poll_job(self, job_id: str) -> dict:
        """Return the current status and captured output for a job.

        The response contains ``job_id``, ``status`` (one of QUEUED,
        RUNNING, COMPLETED, FAILED, TERMINATED), ``stdout``, ``stderr``,
        and ``exit_code`` (``None`` until the job reaches a terminal state).
        """

        async with httpx.AsyncClient(base_url=self._base_url) as client:
            resp = await client.get(f"/jobs/{job_id}")
            resp.raise_for_status()
            return resp.json()

    async def terminate_job(self, job_id: str) -> None:
        """Request termination (SIGTERM) of a running job."""

        async with httpx.AsyncClient(base_url=self._base_url) as client:
            resp = await client.post(f"/jobs/{job_id}/terminate")
            resp.raise_for_status()
