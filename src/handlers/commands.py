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

REGISTER_HINT = "برای شروع، لطفاً از طریق وبسایت ثبت‌نام کنید."

STATUS_FA = "📊 وضعیت شما:\nارسالی‌ها: {count} ({pending} در انتظار)\nرای‌گیری فعال: {active}"
HELP_FA = (
    "🔹 دستورات:\n"
    "وضعیت — وضعیت حساب شما\n"
    "رای — مشاهده رای‌گیری فعال\n"
    "زبان — تغییر زبان\n"
    "انصراف — رد کردن رای‌گیری\n"
    "یا هر متنی بفرستید تا نگرانی شما ثبت شود."
)
NO_ACTIVE_CYCLE_FA = "در حال حاضر رای‌گیری فعالی وجود ندارد."
SKIP_FA = "✅ از این دور رای‌گیری رد شدید."
NOT_ENDORSEMENT_STAGE_FA = "در حال حاضر مرحله امضا فعال نیست."
ENDORSEMENT_RECORDED_FA = "✅ امضای شما ثبت شد."

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
    active_str = "بله" if active else "خیر"

    await channel.send_message(
        OutboundMessage(
            recipient_ref=message.sender_ref,
            text=STATUS_FA.format(count=total, pending=pending, active=active_str),
        )
    )
    return "status_sent"


async def _handle_help(message: UnifiedMessage, channel: BaseChannel) -> str:
    await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=HELP_FA))
    return "help_sent"


async def _handle_vote(user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession) -> str:
    from src.handlers.voting import send_ballot_prompt
    from src.models.cluster import Cluster

    cycle_result = await db.execute(
        select(VotingCycle).where(VotingCycle.status == "active").order_by(VotingCycle.started_at.desc())
    )
    active_cycle = cycle_result.scalars().first()
    if active_cycle is None:
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=NO_ACTIVE_CYCLE_FA))
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


async def _handle_skip(message: UnifiedMessage, channel: BaseChannel) -> str:
    await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=SKIP_FA))
    return "skipped"


async def _handle_sign(user: User, message: UnifiedMessage, channel: BaseChannel, db: AsyncSession) -> str:
    normalized = message.text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    match = _SIGN_PATTERN.match(normalized)
    if not match:
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=NOT_ENDORSEMENT_STAGE_FA))
        return "invalid_sign"

    index = int(match.group(1))
    cycle_result = await db.execute(
        select(VotingCycle).where(VotingCycle.status == "active").order_by(VotingCycle.started_at.desc())
    )
    active_cycle = cycle_result.scalars().first()
    if active_cycle is None or not active_cycle.cluster_ids:
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=NOT_ENDORSEMENT_STAGE_FA))
        return "no_active_cycle"

    if index < 1 or index > len(active_cycle.cluster_ids):
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=NOT_ENDORSEMENT_STAGE_FA))
        return "invalid_index"

    cluster_id = active_cycle.cluster_ids[index - 1]
    ok, status = await record_endorsement(session=db, user=user, cluster_id=cluster_id)
    if ok:
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=ENDORSEMENT_RECORDED_FA))
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

        ok, status = await resolve_linking_code(
            session=session, code=message.text.strip(), account_ref=message.sender_ref,
        )
        if ok:
            return "account_linked"
        await channel.send_message(OutboundMessage(recipient_ref=message.sender_ref, text=REGISTER_HINT))
        return "registration_prompted"

    command = detect_command(message.text)

    if command == "status":
        return await _handle_status(user, message, channel, session)
    if command == "help":
        return await _handle_help(message, channel)
    if command == "vote":
        return await _handle_vote(user, message, channel, session)
    if command == "language":
        return await _handle_language(user, message, channel, session)
    if command == "skip":
        return await _handle_skip(message, channel)
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
            vote, status = await cast_vote(
                session=session,
                user=user,
                cycle=active_cycle,
                approved_cluster_ids=cluster_ids,
                min_account_age_hours=get_settings().min_account_age_hours,
            )
            if vote is None:
                await channel.send_message(
                    OutboundMessage(recipient_ref=message.sender_ref, text=f"Vote rejected: {status}")
                )
                return status
            await channel.send_message(
                OutboundMessage(recipient_ref=message.sender_ref, text="✅ رای شما ثبت شد!")
            )
            return "vote_recorded"

    await handle_submission(message, user, channel, session)
    return "submission_received"
