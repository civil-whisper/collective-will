from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.config import get_settings
from src.db.evidence import append_evidence
from src.db.queries import create_submission
from src.handlers.abuse import check_burst_quarantine, check_submission_rate_limit
from src.models.submission import Submission, SubmissionCreate
from src.models.user import User

HIGH_RISK_PII = [
    re.compile(r"\b\d{10,}\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
]

CONFIRMATION_FA = "✅ دریافت شد! نظر شما ثبت شد.\nمی‌توانید وضعیت آن را در وبسایت ببینید."
PII_WARNING_FA = "⚠️ اطلاعات شخصی شناسایی شد. لطفا اطلاعات خصوصی را حذف کرده و دوباره ارسال کنید."
NOT_ELIGIBLE_FA = "❌ حساب شما هنوز واجد شرایط ارسال نیست."
RATE_LIMIT_FA = "⏳ شما به حداکثر تعداد ارسال روزانه رسیده‌اید."


def detect_high_risk_pii(text: str) -> bool:
    return any(pattern.search(text) for pattern in HIGH_RISK_PII)


def hash_submission(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def eligible_for_submission(user: User, min_account_age_hours: int) -> bool:
    if not user.email_verified:
        return False
    if not user.messaging_verified:
        return False
    if user.messaging_account_age is None:
        return False
    return datetime.now(UTC) - user.messaging_account_age >= timedelta(hours=min_account_age_hours)


async def handle_submission(
    message: UnifiedMessage,
    user: User,
    channel: BaseChannel,
    db: AsyncSession,
) -> None:
    """Full intake handler: eligibility, rate-limit, PII, store, evidence, confirmation."""
    settings = get_settings()
    if not eligible_for_submission(user, settings.min_account_age_hours):
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=NOT_ELIGIBLE_FA))
        return

    allowed, reason = await check_submission_rate_limit(session=db, user_id=user.id)
    if not allowed:
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=RATE_LIMIT_FA))
        return

    if detect_high_risk_pii(message.text):
        await append_evidence(
            session=db,
            event_type="submission_received",
            entity_type="user",
            entity_id=user.id,
            payload={"status": "rejected_high_risk_pii", "reason_code": "high_risk_pii"},
        )
        await db.commit()
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=PII_WARNING_FA))
        return

    submission_hash = hash_submission(message.text)
    submission = await create_submission(
        db,
        SubmissionCreate(
            user_id=user.id,
            raw_text=message.text,
            language=user.locale,
            hash=submission_hash,
        ),
    )

    quarantined = await check_burst_quarantine(session=db, user_id=user.id)
    if quarantined:
        submission.status = "quarantined"

    await append_evidence(
        session=db,
        event_type="submission_received",
        entity_type="submission",
        entity_id=submission.id,
        payload={
            "submission_id": str(submission.id),
            "user_id": str(user.id),
            "hash": submission_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    await db.commit()
    await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=CONFIRMATION_FA))


async def process_submission(
    *,
    session: AsyncSession,
    user: User,
    raw_text: str,
    min_account_age_hours: int,
) -> tuple[Submission | None, str]:
    """Lower-level submission processor (used by route_message)."""
    if not eligible_for_submission(user, min_account_age_hours=min_account_age_hours):
        return None, "not_eligible"

    allowed, reason = await check_submission_rate_limit(session=session, user_id=user.id)
    if not allowed:
        return None, reason or "rate_limited"

    if detect_high_risk_pii(raw_text):
        await append_evidence(
            session=session,
            event_type="submission_received",
            entity_type="user",
            entity_id=user.id,
            payload={"status": "rejected_high_risk_pii", "reason_code": "high_risk_pii"},
        )
        await session.commit()
        return None, "pii_redact_and_resend"

    submission_hash = hash_submission(raw_text)
    submission = await create_submission(
        session,
        SubmissionCreate(
            user_id=user.id,
            raw_text=raw_text,
            language=user.locale,
            hash=submission_hash,
        ),
    )

    quarantined = await check_burst_quarantine(session=session, user_id=user.id)
    if quarantined:
        submission.status = "quarantined"
    await append_evidence(
        session=session,
        event_type="submission_received",
        entity_type="submission",
        entity_id=submission.id,
        payload={"status": submission.status, "hash": submission_hash},
    )
    await session.commit()
    return submission, ("accepted_flagged" if quarantined else "accepted")
