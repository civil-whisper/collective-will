from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.config import get_settings
from src.handlers.intake import handle_submission
from src.handlers.voting import cast_vote, parse_ballot, record_endorsement
from src.models.submission import Submission
from src.models.user import User
from src.models.vote import VotingCycle

# ---------------------------------------------------------------------------
# Pre-auth messages: bilingual (user locale unknown)
# ---------------------------------------------------------------------------
REGISTER_HINT = (
    "Please sign up through the website first.\n"
    "برای شروع، لطفاً از طریق وبسایت ثبت‌نام کنید."
)
USER_ALREADY_LINKED = (
    "⚠️ Your email is already linked to another Telegram account.\n"
    "If you need to change it, please contact support.\n\n"
    "⚠️ حساب ایمیل شما قبلاً به یک اکانت تلگرام دیگر متصل شده است.\n"
    "اگر نیاز به تغییر دارید، لطفاً با پشتیبانی تماس بگیرید."
)
ACCOUNT_ALREADY_LINKED = (
    "⚠️ This Telegram account is already linked to another email.\n"
    "Each Telegram account can only be linked to one email.\n\n"
    "⚠️ این اکانت تلگرام قبلاً به یک ایمیل دیگر متصل شده است.\n"
    "هر اکانت تلگرام فقط می‌تواند به یک ایمیل متصل باشد."
)
ACCOUNT_LINKED_OK = (
    "✅ Your account has been linked successfully! ({email})\n"
    "Type help to see available commands.\n\n"
    "✅ حساب شما با موفقیت متصل شد! ({email})\n"
    "برای مشاهده دستورات، بنویسید: کمک"
)

# ---------------------------------------------------------------------------
# Welcome message: locale-aware, sent after successful account linking
# ---------------------------------------------------------------------------
_WELCOME: dict[str, str] = {
    "fa": (
        "✅ حساب شما با موفقیت متصل شد! ({email})\n\n"
        "به «اراده جمعی» خوش آمدید!\n"
        "اینجا می‌توانید نگرانی‌ها و پیشنهادهای سیاستی خود را ارسال کنید. "
        "هوش مصنوعی پیام شما را ساختاربندی می‌کند، موارد مشابه را گروه‌بندی می‌کند، "
        "و جامعه با رأی‌گیری اولویت‌ها را مشخص می‌کند.\n\n"
        "🔹 دستورات:\n"
        "وضعیت — وضعیت حساب شما\n"
        "رای — مشاهده رای‌گیری فعال\n"
        "زبان — تغییر زبان\n"
        "انصراف — رد کردن رای‌گیری\n\n"
        "یا هر متنی بفرستید تا نگرانی شما ثبت شود."
    ),
    "en": (
        "✅ Your account has been linked successfully! ({email})\n\n"
        "Welcome to Collective Will!\n"
        "Here you can submit your policy concerns and proposals. "
        "AI will structure your message, group similar ideas together, "
        "and the community votes to set priorities.\n\n"
        "🔹 Commands:\n"
        "status — your account status\n"
        "vote — view active vote\n"
        "language — change language\n"
        "skip — skip current vote\n\n"
        "Or send any text to record your concern."
    ),
}


def _welcome_msg(locale: str, **kwargs: str) -> str:
    lang = locale if locale in _WELCOME else "en"
    template = _WELCOME[lang]
    return template.format(**kwargs) if kwargs else template

# ---------------------------------------------------------------------------
# Locale-aware messages (post-auth: user.locale is known)
# ---------------------------------------------------------------------------
_MESSAGES: dict[str, dict[str, str]] = {
    "fa": {
        "status": "📊 وضعیت شما:\nارسالی‌ها: {count} ({pending} در انتظار)\nرای‌گیری فعال: {active}",
        "status_active_yes": "بله",
        "status_active_no": "خیر",
        "help": (
            "🔹 دستورات:\n"
            "وضعیت — وضعیت حساب شما\n"
            "رای — مشاهده رای‌گیری فعال\n"
            "زبان — تغییر زبان\n"
            "انصراف — رد کردن رای‌گیری\n"
            "یا هر متنی بفرستید تا نگرانی شما ثبت شود."
        ),
        "no_active_cycle": "در حال حاضر رای‌گیری فعالی وجود ندارد.",
        "skip": "✅ از این دور رای‌گیری رد شدید.",
        "not_endorsement_stage": "در حال حاضر مرحله امضا فعال نیست.",
        "endorsement_recorded": "✅ امضای شما ثبت شد.",
        "vote_recorded": "✅ رای شما ثبت شد!",
        "vote_rejected": "رای رد شد: {reason}",
    },
    "en": {
        "status": "📊 Your status:\nSubmissions: {count} ({pending} pending)\nActive vote: {active}",
        "status_active_yes": "Yes",
        "status_active_no": "No",
        "help": (
            "🔹 Commands:\n"
            "status — your account status\n"
            "vote — view active vote\n"
            "language — change language\n"
            "skip — skip current vote\n"
            "Or send any text to record your concern."
        ),
        "no_active_cycle": "There is no active vote at this time.",
        "skip": "✅ You skipped this voting round.",
        "not_endorsement_stage": "There is no active endorsement stage at this time.",
        "endorsement_recorded": "✅ Your endorsement has been recorded.",
        "vote_recorded": "✅ Your vote has been recorded!",
        "vote_rejected": "Vote rejected: {reason}",
    },
}


def _msg(locale: str, key: str, **kwargs: str | int) -> str:
    lang = locale if locale in _MESSAGES else "en"
    template = _MESSAGES[lang][key]
    return template.format(**kwargs) if kwargs else template


# Legacy aliases for backward-compatible test imports
HELP_FA = _MESSAGES["fa"]["help"]
STATUS_FA = _MESSAGES["fa"]["status"]
NO_ACTIVE_CYCLE_FA = _MESSAGES["fa"]["no_active_cycle"]
SKIP_FA = _MESSAGES["fa"]["skip"]
NOT_ENDORSEMENT_STAGE_FA = _MESSAGES["fa"]["not_endorsement_stage"]
ENDORSEMENT_RECORDED_FA = _MESSAGES["fa"]["endorsement_recorded"]

_SIGN_PATTERN = re.compile(r"^(?:sign|امضا)\s+(\d+)$", re.IGNORECASE | re.UNICODE)


def detect_command(text: str) -> str | None:
    """Returns command name if text matches a known command, else None."""
    stripped = text.strip()
    lowered = stripped.lower()

    if lowered in {"وضعیت", "status"}:
        return "status"
    if lowered in {"کمک", "help"}:
        return "help"
    if lowered in {"رای", "vote"}:
        return "vote"
    if lowered in {"زبان", "language"}:
        return "language"
    if lowered in {"انصراف", "skip"}:
        return "skip"

    normalized = stripped.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if _SIGN_PATTERN.match(normalized):
        return "sign"

    return None


def is_command(text: str) -> bool:
    return detect_command(text) is not None


async def _handle_status(user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession) -> str:
    total_result = await db.execute(select(func.count(Submission.id)).where(Submission.user_id == user.id))
    total = int(total_result.scalar_one())
    pending_result = await db.execute(
        select(func.count(Submission.id)).where(Submission.user_id == user.id, Submission.status == "pending")
    )
    pending = int(pending_result.scalar_one())

    cycle_result = await db.execute(
        select(VotingCycle).where(VotingCycle.status == "active").order_by(VotingCycle.started_at.desc())
    )
    active = cycle_result.scalars().first()
    active_str = _msg(user.locale, "status_active_yes") if active else _msg(user.locale, "status_active_no")

    await channel.send_message(
        OutboundMessage(
            recipient_ref=message.sender_ref,
            text=_msg(user.locale, "status", count=total, pending=pending, active=active_str),
        )
    )
    return "status_sent"


async def _handle_help(user: User, message: UnifiedMessage, channel: BaseChannel) -> str:
    await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=_msg(user.locale, "help")))
    return "help_sent"


async def _handle_vote(user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession) -> str:
    from src.handlers.voting import send_ballot_prompt
    from src.models.cluster import Cluster

    cycle_result = await db.execute(
        select(VotingCycle).where(VotingCycle.status == "active").order_by(VotingCycle.started_at.desc())
    )
    active_cycle = cycle_result.scalars().first()
    if active_cycle is None:
        await channel.send_message(
            OutboundMessage(recipient_ref=message.sender_ref, text=_msg(user.locale, "no_active_cycle"))
        )
        return "no_active_cycle"

    clusters_result = await db.execute(select(Cluster).where(Cluster.id.in_(active_cycle.cluster_ids)))
    clusters = list(clusters_result.scalars().all())
    await send_ballot_prompt(user, active_cycle, clusters, channel)
    return "ballot_sent"


async def _handle_language(user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession) -> str:
    if user.locale == "fa":
        user.locale = "en"
        await db.commit()
        msg = OutboundMessage(recipient_ref=message.sender_ref, text="Language changed to English.")
        await channel.send_message(msg)
    else:
        user.locale = "fa"
        await db.commit()
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text="زبان به فارسی تغییر کرد."))
    return "language_updated"


async def _handle_skip(user: User, message: UnifiedMessage, channel: BaseChannel) -> str:
    await channel.send_message(
        OutboundMessage(recipient_ref=message.sender_ref, text=_msg(user.locale, "skip"))
    )
    return "skipped"


async def _handle_sign(user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession) -> str:
    locale = user.locale
    normalized = message.text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    match = _SIGN_PATTERN.match(normalized)
    if not match:
        await channel.send_message(
            OutboundMessage(recipient_ref=message.sender_ref, text=_msg(locale, "not_endorsement_stage"))
        )
        return "invalid_sign"

    index = int(match.group(1))
    cycle_result = await db.execute(
        select(VotingCycle).where(VotingCycle.status == "active").order_by(VotingCycle.started_at.desc())
    )
    active_cycle = cycle_result.scalars().first()
    if active_cycle is None or not active_cycle.cluster_ids:
        await channel.send_message(
            OutboundMessage(recipient_ref=message.sender_ref, text=_msg(locale, "not_endorsement_stage"))
        )
        return "no_active_cycle"

    if index < 1 or index > len(active_cycle.cluster_ids):
        await channel.send_message(
            OutboundMessage(recipient_ref=message.sender_ref, text=_msg(locale, "not_endorsement_stage"))
        )
        return "invalid_index"

    cluster_id = active_cycle.cluster_ids[index - 1]
    ok, status = await record_endorsement(session=db, user=user, cluster_id=cluster_id)
    if ok:
        await channel.send_message(
            OutboundMessage(recipient_ref=message.sender_ref, text=_msg(locale, "endorsement_recorded"))
        )
    return status


async def route_message(
    *,
    session: AsyncSession,
    message: UnifiedMessage,
    channel: BaseChannel,
) -> str:
    user_result = await session.execute(
        select(User).where(User.messaging_account_ref == message.sender_ref)
    )
    user = user_result.scalar_one_or_none()

    if user is None:
        from src.handlers.identity import resolve_linking_code

        ok, status, masked_email = await resolve_linking_code(
            session=session, code=message.text.strip(), account_ref=message.sender_ref,
        )
        if ok:
            linked_user_result = await session.execute(
                select(User).where(User.messaging_account_ref == message.sender_ref)
            )
            linked_user = linked_user_result.scalar_one_or_none()
            locale = linked_user.locale if linked_user else "en"
            text = _welcome_msg(locale, email=masked_email or "")
            await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=text))
            return "account_linked"
        if status == "user_already_linked":
            await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=USER_ALREADY_LINKED))
            return status
        if status == "account_already_linked":
            await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=ACCOUNT_ALREADY_LINKED))
            return status
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=REGISTER_HINT))
        return "registration_prompted"

    command = detect_command(message.text)

    if command == "status":
        return await _handle_status(user, message, channel, session)
    if command == "help":
        return await _handle_help(user, message, channel)
    if command == "vote":
        return await _handle_vote(user, message, channel, session)
    if command == "language":
        return await _handle_language(user, message, channel, session)
    if command == "skip":
        return await _handle_skip(user, message, channel)
    if command == "sign":
        return await _handle_sign(user, message, channel, session)

    text = message.text.strip()
    cycle_result = await session.execute(
        select(VotingCycle).where(VotingCycle.status == "active").order_by(VotingCycle.started_at.desc())
    )
    active_cycle = cycle_result.scalars().first()
    if active_cycle is not None and any(ch.isdigit() for ch in text):
        selections = parse_ballot(text, max_options=len(active_cycle.cluster_ids))
        if selections is not None:
            cluster_ids = [active_cycle.cluster_ids[idx - 1] for idx in selections]
            settings = get_settings()
            vote, status = await cast_vote(
                session=session,
                user=user,
                cycle=active_cycle,
                approved_cluster_ids=cluster_ids,
                min_account_age_hours=settings.min_account_age_hours,
                require_contribution=settings.require_contribution_for_vote,
            )
            if vote is None:
                await channel.send_message(
                    OutboundMessage(
                        recipient_ref=message.sender_ref,
                        text=_msg(user.locale, "vote_rejected", reason=status),
                    )
                )
                return status
            await channel.send_message(
                OutboundMessage(recipient_ref=message.sender_ref, text=_msg(user.locale, "vote_recorded"))
            )
            return "vote_recorded"

    await handle_submission(message, user, channel, session)
    return "submission_received"
