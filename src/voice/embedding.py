"""Cloud speaker embedding via Modal serverless function."""

from __future__ import annotations

import base64
import logging

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


async def get_speaker_embedding(audio_bytes: bytes) -> tuple[list[float], str]:
    """Get speaker embedding from Modal serverless function.

    Args:
        audio_bytes: Raw audio (OGG Opus or WAV).

    Returns:
        Tuple of (192-dim embedding, model_version string).

    Raises:
        httpx.HTTPStatusError: On API error after retries.
    """
    settings = get_settings()
    endpoint_url = settings.voice_embedding_endpoint_url
    timeout = settings.voice_embedding_timeout_seconds
    max_retries = settings.voice_cloud_max_retries

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    payload = {"audio_b64": audio_b64}

    headers: dict[str, str] = {"Content-Type": "application/json"}
    auth_token = settings.voice_embedding_auth_token
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(endpoint_url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["embedding"], data["model_version"]
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            last_exc = exc
            logger.warning(
                "Embedding service attempt %d/%d failed after %.1fs timeout (%s: %s)",
                attempt,
                max_retries,
                timeout,
                type(exc).__name__,
                exc,
                extra={
                    "ops_payload": {
                        "provider": "modal_embedding",
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "timeout_seconds": timeout,
                        "endpoint_url": endpoint_url,
                        "exception_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                },
            )

    raise last_exc  # type: ignore[misc]
