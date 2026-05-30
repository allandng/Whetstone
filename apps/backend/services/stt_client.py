"""HTTP client for whisper-server, the local speech-to-text backend.

Sends recorded audio to a whisper.cpp ``whisper-server`` instance over
loopback and returns a transcript. ``whisper-server`` exposes a multipart
``/inference`` endpoint; the configured model name (see :mod:`config`)
selects which Whisper model the server should use, so swapping models is a
config change rather than a code change (mirrors the llama-server client).
"""

from __future__ import annotations

import httpx

from config import get_settings

_INFERENCE_PATH = "/inference"


class STTUnavailableError(RuntimeError):
    """Raised when whisper-server cannot be reached or returns an error.

    Voice input must fail loudly rather than silently degrading: a stopped or
    misconfigured whisper-server is a setup problem the user needs to see, not
    something to paper over with an empty transcript. Mirrors
    :class:`services.llm_client.LLMUnavailableError`.
    """


class STTClient:
    """Thin async HTTP client around the local whisper-server API."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.stt_base_url
        self._model = settings.stt_model
        # Connect quickly so an unreachable server surfaces fast, but allow a
        # long read window because local transcription can take a while.
        self._timeout = httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0)

    async def transcribe(self, audio: bytes, language: str = "en") -> str:
        """Transcribe ``audio`` bytes to text via whisper-server.

        Raises :class:`STTUnavailableError` if whisper-server cannot be reached
        or responds with an error status.
        """

        files = {"file": ("audio", audio, "application/octet-stream")}
        data = {
            "model": self._model,
            "language": language,
            "response_format": "json",
            "temperature": "0.0",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                resp = await client.post(_INFERENCE_PATH, files=files, data=data)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.RequestError as exc:
            raise STTUnavailableError(
                f"Could not reach whisper-server at {self._base_url}: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise STTUnavailableError(
                f"whisper-server at {self._base_url} returned HTTP "
                f"{exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

        return (payload.get("text") or "").strip()
