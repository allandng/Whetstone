"""HTTP client for llama-server, the local LLM backend.

Talks to a llama.cpp ``llama-server`` instance over loopback to produce
completions for the tutor/co-pilot features. The configured model name
(see :mod:`config`) selects which model the server should use.

Stub: method bodies are not implemented yet.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from config import get_settings


class LLMClient:
    """Thin async HTTP client around the local llama-server API."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.llm_base_url
        self._model = settings.llm_model

    async def complete(self, prompt: str, **kwargs) -> str:
        """Return a single completion for ``prompt``.

        Stub.
        """

        raise NotImplementedError

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Yield completion tokens as they are produced.

        Stub.
        """

        raise NotImplementedError
        yield  # pragma: no cover  (marks this as an async generator)

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url)
