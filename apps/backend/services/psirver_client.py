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


class PsirverUnavailableError(RuntimeError):
    """Raised when Psirver cannot be reached or returns an error.

    Mirrors :class:`services.llm_client.LLMUnavailableError` and
    :class:`services.stt_client.STTUnavailableError` so a dead or misconfigured
    code-execution service is surfaced as a typed failure the caller can map to
    a clean response, rather than a raw transport error bubbling up as a 500.
    """


class PsirverClient:
    """Thin async HTTP client around the Psirver job API."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or get_settings().psirver_base_url
        # Bound every call: connect fast so an unreachable Psirver surfaces
        # quickly, and cap reads so a hung job-control request can't pin a
        # backend request open indefinitely. These are control-plane calls
        # (upload / start / poll / terminate), not long-running generation, so
        # the read window stays short unlike the LLM/STT clients.
        self._timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)

    async def submit_job(self, language: str, source: str) -> str:
        """Upload `source` and start it asynchronously; return the job id.

        Uploads the script (``POST /scripts/upload``) and then kicks off a
        non-blocking run (``POST /scripts/{id}/run``), which replies 202
        Accepted with the job id. Use :meth:`poll_job` to await completion.

        Raises :class:`PsirverUnavailableError` if Psirver cannot be reached or
        responds with an error status; :class:`ValueError` for an unsupported
        language.
        """

        try:
            lang, filename = _LANGUAGES[language.strip().lower()]
        except KeyError as exc:
            raise ValueError(f"unsupported language: {language!r}") from exc

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
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
        except httpx.RequestError as exc:
            raise _unreachable(self._base_url, exc) from exc
        except httpx.HTTPStatusError as exc:
            raise _bad_status(self._base_url, exc) from exc

    async def poll_job(self, job_id: str) -> dict:
        """Return the current status and captured output for a job.

        The response contains ``job_id``, ``status`` (one of QUEUED,
        RUNNING, COMPLETED, FAILED, TERMINATED), ``stdout``, ``stderr``,
        and ``exit_code`` (``None`` until the job reaches a terminal state).

        Raises :class:`PsirverUnavailableError` if Psirver cannot be reached or
        responds with an error status.
        """

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                resp = await client.get(f"/jobs/{job_id}")
                resp.raise_for_status()
                return resp.json()
        except httpx.RequestError as exc:
            raise _unreachable(self._base_url, exc) from exc
        except httpx.HTTPStatusError as exc:
            raise _bad_status(self._base_url, exc) from exc

    async def terminate_job(self, job_id: str) -> None:
        """Request termination (SIGTERM) of a running job.

        Raises :class:`PsirverUnavailableError` if Psirver cannot be reached or
        responds with an error status.
        """

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                resp = await client.post(f"/jobs/{job_id}/terminate")
                resp.raise_for_status()
        except httpx.RequestError as exc:
            raise _unreachable(self._base_url, exc) from exc
        except httpx.HTTPStatusError as exc:
            raise _bad_status(self._base_url, exc) from exc


def _unreachable(base_url: str, exc: httpx.RequestError) -> PsirverUnavailableError:
    return PsirverUnavailableError(f"Could not reach Psirver at {base_url}: {exc}")


def _bad_status(
    base_url: str, exc: httpx.HTTPStatusError
) -> PsirverUnavailableError:
    return PsirverUnavailableError(
        f"Psirver at {base_url} returned HTTP "
        f"{exc.response.status_code}: {exc.response.text[:200]}"
    )
