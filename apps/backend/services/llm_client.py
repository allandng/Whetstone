"""HTTP client for llama-server, the local LLM backend.

Talks to a llama.cpp ``llama-server`` instance over loopback to produce
completions for the tutor/co-pilot features. ``llama-server`` exposes an
OpenAI-compatible ``/v1/chat/completions`` endpoint; the configured model
name (see :mod:`config`) selects which model the server should use, so
swapping models is a config change rather than a code change (FR-AI-7).
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from config import get_settings

_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

# Injected as a system message when ``thinking=True`` so the model reasons
# in depth before answering (FR-AI-8, e.g. complexity analysis).
_THINKING_INSTRUCTION = (
    "Think step by step before you answer. Work through the problem, the "
    "relevant cases, and any intermediate steps explicitly, then state your "
    "final answer clearly at the end."
)


class LLMUnavailableError(RuntimeError):
    """Raised when llama-server cannot be reached or returns an error.

    The co-pilot must fail loudly rather than silently degrading: a stopped
    or misconfigured llama-server is a setup problem the user needs to see,
    not something to paper over with an empty reply.
    """


class LLMClient:
    """Thin async HTTP client around the local llama-server API."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.llm_base_url
        self._model = settings.llm_model
        # Connect quickly so an unreachable server surfaces fast, but allow a
        # long read window because local token generation can take a while.
        self._timeout = httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0)

    async def ask(
        self,
        messages: list[dict],
        stream: bool = False,
        thinking: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Send ``messages`` to llama-server and yield the response text.

        When ``stream`` is true, yields incremental text deltas as the model
        produces them; otherwise yields the full reply as a single chunk.
        When ``thinking`` is true, a system instruction asking for extended
        reasoning is added to the request.

        Raises :class:`LLMUnavailableError` if llama-server cannot be reached
        or responds with an error status.
        """

        body = {
            "model": self._model,
            "messages": _with_thinking(messages) if thinking else messages,
            "stream": stream,
        }
        generator = self._stream(body) if stream else self._once(body)
        async for chunk in generator:
            yield chunk

    async def _once(self, body: dict) -> AsyncGenerator[str, None]:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                resp = await client.post(_CHAT_COMPLETIONS_PATH, json=body)
                resp.raise_for_status()
                data = resp.json()
        except httpx.RequestError as exc:
            raise LLMUnavailableError(
                f"Could not reach llama-server at {self._base_url}: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUnavailableError(
                f"llama-server at {self._base_url} returned HTTP "
                f"{exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

        choices = data.get("choices") or [{}]
        yield choices[0].get("message", {}).get("content", "")

    async def _stream(self, body: dict) -> AsyncGenerator[str, None]:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout
            ) as client:
                async with client.stream(
                    "POST", _CHAT_COMPLETIONS_PATH, json=body
                ) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread())[:200].decode(
                            "utf-8", "replace"
                        )
                        raise LLMUnavailableError(
                            f"llama-server at {self._base_url} returned HTTP "
                            f"{resp.status_code}: {detail}"
                        )
                    async for line in resp.aiter_lines():
                        delta = _parse_sse_line(line)
                        if delta:
                            yield delta
        except httpx.RequestError as exc:
            raise LLMUnavailableError(
                f"Could not reach llama-server at {self._base_url}: {exc}"
            ) from exc


def _with_thinking(messages: list[dict]) -> list[dict]:
    """Return ``messages`` with the extended-reasoning instruction inserted.

    The instruction is placed after any leading system messages so it stays
    grouped with the rest of the system context rather than displacing it.
    """

    idx = 0
    for message in messages:
        if message.get("role") == "system":
            idx += 1
        else:
            break
    thinking_message = {"role": "system", "content": _THINKING_INSTRUCTION}
    return [*messages[:idx], thinking_message, *messages[idx:]]


def _parse_sse_line(line: str) -> str | None:
    """Extract the content delta from one OpenAI-style SSE line, if any."""

    line = line.strip()
    if not line or not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if data == "[DONE]":
        return None
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = obj.get("choices")
    if not choices:
        return None
    return choices[0].get("delta", {}).get("content") or None
