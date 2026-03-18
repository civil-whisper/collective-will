"""Cloud transcription via OpenAI GPT-4o-transcribe API."""

from __future__ import annotations

import logging

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

# OpenAI audio transcription endpoint
_OPENAI_AUDIO_URL = "https://api.openai.com/v1/audio/transcriptions"


async def transcribe_audio(audio_bytes: bytes, language: str | None = None) -> str:
    """Transcribe audio bytes using OpenAI GPT-4o-transcribe.

    Args:
        audio_bytes: Raw audio (OGG Opus or WAV).
        language: ISO-639-1 code (e.g. 'en', 'fa'). Improves accuracy.

    Returns:
        Transcribed text (stripped of leading/trailing whitespace).

    Raises:
        httpx.HTTPStatusError: On API error after retries.
    """
    settings = get_settings()
    timeout = settings.voice_transcription_timeout_seconds
    max_retries = settings.voice_cloud_max_retries

    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                # OpenAI expects multipart form data with a file field
                files = {"file": ("audio.ogg", audio_bytes, "audio/ogg")}
                data: dict[str, str] = {"model": "gpt-4o-transcribe"}
                if language:
                    data["language"] = language.strip().lower()

                resp = await client.post(
                    _OPENAI_AUDIO_URL,
                    headers=headers,
                    files=files,
                    data=data,
                )
                resp.raise_for_status()
                result = resp.json()
                text: str = result["text"]
                return text.strip()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            last_exc = exc
            logger.warning(
                "OpenAI transcription attempt %d/%d failed after %.1fs timeout (%s: %s)",
                attempt,
                max_retries,
                timeout,
                type(exc).__name__,
                exc,
                extra={
                    "ops_payload": {
                        "provider": "openai_transcription",
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "timeout_seconds": timeout,
                        "exception_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                },
            )

    raise last_exc  # type: ignore[misc]
