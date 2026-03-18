"""Voice processing client: cloud transcription + cloud embedding + local scoring."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, cast

from src.voice.embedding import get_speaker_embedding
from src.voice.transcription import transcribe_audio
from src.voice.transcription_scoring import score_transcription

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceProcessResult:
    transcription: str
    transcription_score: float
    embedding: list[float]
    model_version: str


VoiceProvider = Literal["openai_transcription", "modal_embedding", "multiple"]


class VoiceProviderError(RuntimeError):
    """Wrap upstream voice failures with provider context."""

    def __init__(
        self,
        *,
        provider: VoiceProvider,
        cause: Exception,
        secondary_cause: Exception | None = None,
    ) -> None:
        self.provider = provider
        self.cause = cause
        self.secondary_cause = secondary_cause

        message = f"{provider} failed ({type(cause).__name__}: {cause})"
        if secondary_cause is not None:
            message += f"; secondary failure ({type(secondary_cause).__name__}: {secondary_cause})"
        super().__init__(message)


class VoiceCloudClient:
    """Calls OpenAI for transcription + Modal for embedding, scores locally."""

    async def process_audio(
        self,
        audio_bytes: bytes,
        expected_phrase: str,
        language: str | None = None,
    ) -> VoiceProcessResult:
        """Process audio: transcribe (OpenAI) + embed (Modal) in parallel, score locally.

        Raises on API failure after retries.
        """
        lang = (language or "en").strip().lower()

        # Run transcription and embedding in parallel
        transcript_task = asyncio.create_task(transcribe_audio(audio_bytes, language=lang))
        embedding_task = asyncio.create_task(get_speaker_embedding(audio_bytes))

        transcript_result, embedding_result = await asyncio.gather(
            transcript_task, embedding_task, return_exceptions=True
        )

        transcript_exc = transcript_result if isinstance(transcript_result, Exception) else None
        embedding_exc = embedding_result if isinstance(embedding_result, Exception) else None

        if transcript_exc is not None or embedding_exc is not None:
            if transcript_exc is not None:
                logger.error(
                    "Voice processing upstream failed: OpenAI transcription",
                    extra={
                        "ops_payload": {
                            "provider": "openai_transcription",
                            "exception_type": type(transcript_exc).__name__,
                            "error_message": str(transcript_exc),
                        }
                    },
                    exc_info=(
                        type(transcript_exc),
                        transcript_exc,
                        transcript_exc.__traceback__,
                    ),
                )
            if embedding_exc is not None:
                logger.error(
                    "Voice processing upstream failed: Modal embedding",
                    extra={
                        "ops_payload": {
                            "provider": "modal_embedding",
                            "exception_type": type(embedding_exc).__name__,
                            "error_message": str(embedding_exc),
                        }
                    },
                    exc_info=(
                        type(embedding_exc),
                        embedding_exc,
                        embedding_exc.__traceback__,
                    ),
                )

            if transcript_exc is not None and embedding_exc is not None:
                raise VoiceProviderError(
                    provider="multiple",
                    cause=transcript_exc,
                    secondary_cause=embedding_exc,
                )
            if transcript_exc is not None:
                raise VoiceProviderError(
                    provider="openai_transcription",
                    cause=transcript_exc,
                )
            assert embedding_exc is not None
            raise VoiceProviderError(
                provider="modal_embedding",
                cause=embedding_exc,
            )

        transcript = cast(str, transcript_result)
        embedding, model_version = cast(tuple[list[float], str], embedding_result)

        score = score_transcription(transcript, expected_phrase, lang)

        return VoiceProcessResult(
            transcription=transcript,
            transcription_score=score,
            embedding=embedding,
            model_version=model_version,
        )
