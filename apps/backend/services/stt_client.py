"""HTTP client for whisper-server, the local speech-to-text backend.

Sends recorded audio to a whisper.cpp ``whisper-server`` instance over
loopback and returns a transcript. The configured model name (see
:mod:`config`) selects which Whisper model the server should use.

Stub: method bodies are not implemented yet.
"""

from __future__ import annotations

import httpx

from config import get_settings


class STTClient:
    """Thin async HTTP client around the local whisper-server API."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.stt_base_url
        self._model = settings.stt_model

    async def transcribe(self, audio: bytes, language: str = "en") -> str:
        """Transcribe ``audio`` bytes to text.

        Stub.
        """

        raise NotImplementedError

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url)
