from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.config import get_settings
from src.db.evidence import append_evidence
from src.db.queries import create_policy_candidate, create_submission
from src.handlers.abuse import check_burst_quarantine, check_submission_rate_limit
from src.models.submission import Submission, SubmissionCreate
from src.models.user import User
from src.pipeline.canonicalize import CanonicalizationRejection, canonicalize_single
from src.pipeline.embeddings import compute_and_store_embeddings
from src.pipeline.llm import LLMRouter

logger = logging.getLogger(__name__)

HIGH_RISK_PII = [
    re.compile(r"\b\d{10,}\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
]

_MESSAGES = {
    "fa": {
        "confirmation": (
            "✅ دریافت شد! نظر شما ثبت شد.\n"
            "ما پیام شما را اینطور فهمیدیم: «{title}»\n"
            "📊 مشاهده در وبسایت: {url}"
        ),
        "confirmation_fallback": (
            "✅ دریافت شد! نظر شما ثبت شد.\n"
            "📊 مشاهده در وبسایت: {url}"
        ),
        "rejection": (
            "❌ پیام شما به عنوان یک پیشنهاد سیاستی قابل پردازش نبود.\n"
            "{reason}\n"
            "لطفاً یک پیشنهاد مشخص درباره حکمرانی، قوانین، حقوق، یا امور عمومی ارسال کنید."
        ),
        "pii_warning": "⚠️ اطلاعات شخصی شناسایی شد. لطفا اطلاعات خصوصی را حذف کرده و دوباره ارسال کنید.",
        "not_eligible": "❌ حساب شما هنوز واجد شرایط ارسال نیست.",
        "rate_limit": "⏳ شما به حداکثر تعداد ارسال روزانه رسیده‌اید.",
    },
    "en": {
        "confirmation": (
            "✅ Received! Your submission has been recorded.\n"
            'We understood it as: "{title}"\n'
            "📊 View on website: {url}"
        ),
        "confirmation_fallback": (
            "✅ Received! Your submission has been recorded.\n"
            "📊 View on website: {url}"
        ),
        "rejection": (
            "❌ Your message could not be processed as a policy proposal.\n"
            "{reason}\n"
            "Please submit a clear proposal about governance, laws, rights, or public affairs."
        ),
        "pii_warning": "⚠️ Personal information detected. Please remove private data and try again.",
        "not_eligible": "❌ Your account is not yet eligible for submissions.",
        "rate_limit": "⏳ You have reached the daily submission limit.",
    },
}


def _msg(locale: str, key: str, **kwargs: str) -> str:
    lang = locale if locale in _MESSAGES else "en"
    template = _MESSAGES[lang][key]
    return template.format(**kwargs) if kwargs else template


NOT_ELIGIBLE_FA = _MESSAGES["fa"]["not_eligible"]
PII_WARNING_FA = _MESSAGES["fa"]["pii_warning"]
RATE_LIMIT_FA = _MESSAGES["fa"]["rate_limit"]
REJECTION_FA = _MESSAGES["fa"]["rejection"]


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
    llm_router: LLMRouter | None = None,
) -> None:
    """Full intake handler: eligibility, rate-limit, PII, store, canonicalize, embed, confirm."""
    settings = get_settings()
    locale = user.locale or "en"

    if not eligible_for_submission(user, settings.min_account_age_hours):
        await channel.send_message(
            OutboundMessage(recipient_ref=message.sender_ref, text=_msg(locale, "not_eligible"))
        )
        return

    allowed, reason = await check_submission_rate_limit(session=db, user_id=user.id)
    if not allowed:
        await channel.send_message(
            OutboundMessage(recipient_ref=message.sender_ref, text=_msg(locale, "rate_limit"))
        )
        return

    if detect_high_risk_pii(message.text):
        await append_evidence(
            session=db,
            event_type="submission_received",
            entity_type="user",
            entity_id=user.id,
            payload={
                "status": "rejected_high_risk_pii",
                "reason_code": "high_risk_pii",
                "user_id": str(user.id),
                "language": locale,
            },
        )
        await db.commit()
        await channel.send_message(
            OutboundMessage(recipient_ref=message.sender_ref, text=_msg(locale, "pii_warning"))
        )
        return

    submission_hash = hash_submission(message.text)
    submission = await create_submission(
        db,
        SubmissionCreate(
            user_id=user.id,
            raw_text=message.text,
            language=locale,
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
            "raw_text": message.text,
            "language": locale,
            "status": submission.status,
            "hash": submission_hash,
        },
    )

    router = llm_router or LLMRouter(settings=settings)
    try:
        result = await canonicalize_single(
            session=db,
            submission_id=submission.id,
            raw_text=message.text,
            language=locale,
            llm_router=router,
        )

        if isinstance(result, CanonicalizationRejection):
            submission.status = "rejected"
            await db.commit()
            text = _msg(locale, "rejection", reason=result.reason)
            await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=text))
            return

        db_candidate = await create_policy_candidate(db, result)
        await compute_and_store_embeddings(session=db, candidates=[db_candidate], llm_router=router)
        submission.status = "canonicalized"
        await db.commit()
        analytics_url = f"{settings.app_public_base_url}/{locale}/collective-concerns#candidate-{db_candidate.id}"
        text = _msg(locale, "confirmation", title=result.title, url=analytics_url)
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=text))
    except Exception:
        logger.exception("Inline canonicalization failed for submission %s, deferring to batch", submission.id)
        submission.status = "pending"
        await db.commit()
        analytics_url = f"{settings.app_public_base_url}/{locale}/collective-concerns"
        await channel.send_message(
            OutboundMessage(
                recipient_ref=message.sender_ref,
                text=_msg(locale, "confirmation_fallback", url=analytics_url),
            )
        )


async def process_submission(
    *,
    session: AsyncSession,
    user: User,
    raw_text: str,
    min_account_age_hours: int,
    llm_router: LLMRouter | None = None,
) -> tuple[Submission | None, str]:
    """Lower-level submission processor (used by route_message).

    Returns (submission, status_code) where status_code is one of:
    accepted, accepted_flagged, rejected_not_policy, pending (LLM fallback),
    not_eligible, rate_limited, pii_redact_and_resend.
    """
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
            payload={
                "status": "rejected_high_risk_pii",
                "reason_code": "high_risk_pii",
                "user_id": str(user.id),
                "language": user.locale,
            },
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
        payload={
            "submission_id": str(submission.id),
            "user_id": str(user.id),
            "raw_text": raw_text,
            "language": user.locale,
            "status": submission.status,
            "hash": submission_hash,
        },
    )

    settings = get_settings()
    router = llm_router or LLMRouter(settings=settings)
    try:
        result = await canonicalize_single(
            session=session,
            submission_id=submission.id,
            raw_text=raw_text,
            language=user.locale,
            llm_router=router,
        )

        if isinstance(result, CanonicalizationRejection):
            submission.status = "rejected"
            await session.commit()
            return submission, "rejected_not_policy"

        db_candidate = await create_policy_candidate(session, result)
        await compute_and_store_embeddings(session=session, candidates=[db_candidate], llm_router=router)
        submission.status = "canonicalized"
        await session.commit()
        return submission, ("accepted_flagged" if quarantined else "accepted")
    except Exception:
        logger.exception("Inline canonicalization failed for submission %s, deferring to batch", submission.id)
        submission.status = "pending"
        await session.commit()
        return submission, "pending"
