"""Routes for AI tutor / co-pilot interactions.

Stub endpoints that will bridge the frontend to the local LLM
(:class:`services.llm_client.LLMClient`) and speech-to-text
(:class:`services.stt_client.STTClient`) backends.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/chat")
async def chat() -> dict:
    """Send a tutor message and receive a reply. Stub."""

    return {}


@router.post("/transcribe")
async def transcribe() -> dict:
    """Transcribe uploaded audio to text via whisper-server. Stub."""

    return {}
