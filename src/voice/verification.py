"""Voice session verification: compare audio against stored enrollment embedding."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.base import BaseChannel
from src.config import get_settings
from src.db.evidence import append_evidence
from src.models.user import User
from src.voice.audio import AudioValidationError, download_and_validate_audio
from src.voice.client import VoiceCloudClient, VoiceProviderError
from src.voice.errors import VoiceErrorCode
from src.voice.phrases import get_phrase, select_phrases
from src.voice.scoring import cosine_similarity, deserialize_embedding, voice_decision

logger = logging.getLogger(__name__)

VerificationResult = Literal["accept", "reject", "audio_error", "service_error"]
# User-facing validation reasons (too_short/too_long) or technical code (V002–V004)
VerificationErrorReason = Literal["too_short", "too_long"] | VoiceErrorCode
VerificationOutcome = tuple[VerificationResult, VerificationErrorReason | None]


def pick_verification_phrase(locale: str) -> tuple[int, str]:
    """Select a single random phrase for verification."""
    ids = select_phrases(locale=locale, count=1)
    phrase_id = ids[0]
    return phrase_id, get_phrase(locale, phrase_id)


async def verify_voice(
    *,
    user: User,
    channel: BaseChannel,
    file_id: str,
    duration: int | None,
    phrase_id: int,
    session: AsyncSession,
) -> VerificationOutcome:
    """Verify a voice message against the user's stored enrollment embedding.

    Returns (result, error_code). error_code is set only for audio_error/service_error.
    Updates user.voice_verified_at on accept. Logs evidence. Caller commits.
    """
    settings = get_settings()

    if user.voice_embedding is None:
        return ("reject", None)

    phrase_id = int(phrase_id)

    # Download and validate
    try:
        audio_bytes = await download_and_validate_audio(channel, file_id, duration)
    except AudioValidationError as e:
        logger.warning("Verification audio validation failed (%s)", e.reason)
        reason: Literal["too_short", "too_long"] = (
            "too_short" if e.reason == "too_short" else "too_long"
        )
        return ("audio_error", reason)
    except Exception as e:
        logger.exception(
            "Verification audio_error V002: download failed (%s: %s)",
            type(e).__name__,
            e,
        )
        return ("audio_error", "V002")

    # Call voice service
    client = VoiceCloudClient()
    phrase_text = get_phrase(user.locale, phrase_id)
    try:
        result = await client.process_audio(
            audio_bytes, phrase_text, language=user.locale
        )
    except VoiceProviderError as e:
        logger.exception(
            "Verification service_error V003: process_audio failed [%s] (%s: %s)",
            e.provider,
            type(e.cause).__name__,
            e.cause,
        )
        return ("service_error", "V003")
    except Exception as e:
        logger.exception(
            "Verification service_error V003: process_audio failed (%s: %s)",
            type(e).__name__,
            e,
        )
        return ("service_error", "V003")

    # Compare against stored embedding (may raise on dimension mismatch or bad data)
    try:
        stored_embedding = deserialize_embedding(user.voice_embedding)
        sim = cosine_similarity(result.embedding, stored_embedding)
    except Exception as e:
        logger.exception(
            "Verification service_error V004: scoring failed (%s: %s)",
            type(e).__name__,
            e,
        )
        return ("service_error", "V004")

    # Unified thresholds (ECAPA2 + GPT-4o-transcribe perform equally across EN/FA)
    trans_standard = settings.voice_transcription_score_standard
    trans_strict = settings.voice_transcription_score_strict
    sim_high = settings.voice_embedding_similarity_high
    sim_moderate = sim_high - settings.voice_embedding_similarity_delta

    decision = voice_decision(
        embedding_similarity=sim,
        transcription_score=result.transcription_score,
        sim_high=sim_high,
        sim_moderate=sim_moderate,
        trans_standard=trans_standard,
        trans_strict=trans_strict,
    )

    # Log evidence (no biometric data — only scores and phrase_id)
    await append_evidence(
        session=session,
        event_type="voice_verified",
        entity_type="user",
        entity_id=user.id,
        payload={
            "decision": decision,
            "embedding_similarity": round(sim, 4),
            "transcription_score": round(result.transcription_score, 4),
            "phrase_id": phrase_id,
            "trans_standard": trans_standard,
            "trans_strict": trans_strict,
        },
    )

    if decision == "accept":
        user.voice_verified_at = datetime.now(UTC)
        return ("accept", None)

    return ("reject", None)
