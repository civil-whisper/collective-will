"""Voice enrollment state machine.

Multi-step enrollment: user reads N phrases, embeddings are collected and averaged.
State stored in user.bot_state_data. Callers are responsible for DB commits.
"""

from __future__ import annotations

import base64
import logging
import struct
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.base import BaseChannel
from src.config import get_settings
from src.db.evidence import append_evidence
from src.models.enrollment_audio import EnrollmentAudio
from src.models.user import User
from src.voice.audio import AudioValidationError, download_and_validate_audio
from src.voice.client import VoiceCloudClient, VoiceProviderError
from src.voice.phrases import get_phrase, select_phrases
from src.voice.scoring import average_embeddings, serialize_embedding

logger = logging.getLogger(__name__)

EnrollmentStatus = Literal[
    "phrase_prompt",      # Sent next phrase prompt to user
    "phrase_accepted",    # Audio accepted, moving to next phrase
    "phrase_retry",       # Audio rejected, user can retry
    "phrase_replaced",    # Too many retries on this phrase, replaced with new one
    "enrollment_complete",  # All phrases collected, enrollment finalized
    "enrollment_blocked",   # Too many total failures, blocked until tomorrow
    "audio_error",        # Audio validation or download error
    "service_error",      # Voice service unreachable
]


def init_enrollment_state(locale: str, exclude_ids: list[int] | None = None) -> dict[str, Any]:
    """Create initial enrollment bot_state_data."""
    settings = get_settings()
    phrase_ids = select_phrases(
        locale=locale,
        count=settings.voice_enrollment_phrases_per_session,
        exclude_ids=exclude_ids,
    )
    return {
        "enrollment": True,
        "step": 0,
        "phrase_ids": phrase_ids,
        "collected_embeddings": [],
        "attempt": 0,
        "failures": 0,
        "failed_phrase_ids": exclude_ids or [],
    }


async def start_enrollment(user: User) -> dict[str, Any]:
    """Initialize enrollment state and return it. Caller sets bot_state/bot_state_data."""
    state = init_enrollment_state(user.locale)
    return state


def get_current_phrase(state: dict[str, Any], locale: str) -> tuple[int, str]:
    """Get the current phrase ID and text from enrollment state."""
    step = state["step"]
    phrase_id = state["phrase_ids"][step]
    return phrase_id, get_phrase(locale, phrase_id)


async def process_enrollment_audio(
    *,
    user: User,
    state: dict[str, Any],
    channel: BaseChannel,
    file_id: str,
    duration: int | None,
    session: AsyncSession,
) -> tuple[EnrollmentStatus, dict[str, Any]]:
    """Process one voice message during enrollment.

    Returns (status, updated_state). Caller must persist state and commit.
    """
    settings = get_settings()
    locale = user.locale

    # Download and validate audio
    try:
        audio_bytes = await download_and_validate_audio(channel, file_id, duration)
    except AudioValidationError:
        return "audio_error", state
    except Exception:
        logger.exception("Failed to download audio for enrollment")
        return "audio_error", state

    # Call voice service
    client = VoiceCloudClient()
    try:
        phrase_id, phrase_text = get_current_phrase(state, locale)
        result = await client.process_audio(audio_bytes, phrase_text, language=locale)
    except VoiceProviderError as e:
        logger.exception(
            "Voice service error during enrollment [%s] (%s: %s)",
            e.provider,
            type(e.cause).__name__,
            e.cause,
        )
        return "service_error", state
    except Exception:
        logger.exception("Voice service error during enrollment")
        return "service_error", state

    # During enrollment, we only check transcription match (no stored embedding yet)
    # Use strict threshold so we only accept high-confidence readings → better-quality signature
    trans_strict = settings.voice_transcription_score_strict
    if result.transcription_score >= trans_strict:
        # Phrase accepted — store embedding and audio
        emb_b64 = base64.b64encode(
            bytes(struct.pack(f"<{len(result.embedding)}f", *result.embedding))
        ).decode("ascii")
        state["collected_embeddings"].append(emb_b64)
        # Store raw audio for model portability (base64 in state, persisted on finalize)
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        state.setdefault("collected_audio", []).append(audio_b64)
        state["model_version"] = result.model_version
        state["attempt"] = 0
        state["step"] += 1

        # Check if enrollment is complete
        if state["step"] >= len(state["phrase_ids"]):
            return "enrollment_complete", state

        return "phrase_accepted", state

    # Phrase rejected — log score for debugging/tuning, then increment attempt
    await append_evidence(
        session=session,
        event_type="voice_enroll_phrase_rejected",
        entity_type="user",
        entity_id=user.id,
        payload={
            "transcription_score": round(result.transcription_score, 4),
            "trans_strict": trans_strict,
            "phrase_id": phrase_id,
            "attempt": state["attempt"] + 1,
        },
    )
    state["attempt"] += 1

    if state["attempt"] >= settings.voice_enrollment_attempts_per_phrase:
        # Too many attempts on this phrase → replace it
        state["failures"] += 1
        state["failed_phrase_ids"].append(state["phrase_ids"][state["step"]])

        if state["failures"] >= settings.voice_enrollment_max_phrase_failures:
            return "enrollment_blocked", state

        # Replace current phrase with a new one
        try:
            new_ids = select_phrases(
                locale=locale,
                count=1,
                exclude_ids=state["failed_phrase_ids"] + state["phrase_ids"],
            )
            state["phrase_ids"][state["step"]] = new_ids[0]
            state["attempt"] = 0
            return "phrase_replaced", state
        except ValueError:
            # Not enough phrases left
            return "enrollment_blocked", state

    return "phrase_retry", state


async def finalize_enrollment(
    user: User, state: dict[str, Any], session: AsyncSession,
) -> None:
    """Average collected embeddings and store on user. Caller commits."""
    embeddings: list[list[float]] = []
    for emb_b64 in state["collected_embeddings"]:
        raw = base64.b64decode(emb_b64)
        count = len(raw) // 4
        emb = list(struct.unpack(f"<{count}f", raw))
        embeddings.append(emb)

    avg = average_embeddings(embeddings)
    user.voice_embedding = serialize_embedding(avg)
    user.voice_enrolled_at = datetime.now(UTC)
    user.voice_verified_at = datetime.now(UTC)
    user.voice_model_version = state.get("model_version", "Jenthe/ECAPA2")

    # Persist raw enrollment audio for model portability
    for i, audio_b64 in enumerate(state.get("collected_audio", [])):
        phrase_id = state["phrase_ids"][i] if i < len(state["phrase_ids"]) else 0
        session.add(EnrollmentAudio(
            user_id=user.id,
            phrase_id=phrase_id,
            audio_ogg=base64.b64decode(audio_b64),
        ))

    await append_evidence(
        session=session,
        event_type="voice_enrolled",
        entity_type="user",
        entity_id=user.id,
        payload={
            "phrases_used": len(state["collected_embeddings"]),
            "model_version": user.voice_model_version,
        },
    )
