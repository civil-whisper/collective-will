from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage
from src.config import get_settings
from src.db.evidence import append_evidence
from src.db.queries import (
    count_votes_for_cluster,
    create_policy_endorsement,
    create_vote,
    create_voting_cycle,
)
from src.handlers.abuse import can_change_vote
from src.models.endorsement import PolicyEndorsementCreate
from src.models.user import User
from src.models.vote import Vote, VoteCreate, VotingCycle, VotingCycleCreate

FARSI_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def parse_ballot(text: str, max_options: int | None = None) -> list[int] | None:
    """Parse user reply into 1-based option indices. Returns None if unparseable."""
    normalized = text.translate(FARSI_DIGITS).replace("،", ",")
    values: list[int] = []
    for token in normalized.replace(" ", ",").split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            val = int(token)
            if max_options is not None and (val < 1 or val > max_options):
                return None
            values.append(val)
        else:
            return None
    return values if values else None


def eligible_for_submission_or_endorsement(user: User) -> bool:
    settings = get_settings()
    if not user.email_verified:
        return False
    if not user.messaging_verified:
        return False
    if user.messaging_account_age is None:
        return False
    return datetime.now(UTC) - user.messaging_account_age >= timedelta(
        hours=settings.min_account_age_hours
    )


def eligible_for_vote(
    user: User, min_account_age_hours: int, require_contribution: bool = True
) -> bool:
    if not user.email_verified:
        return False
    if not user.messaging_verified:
        return False
    if user.messaging_account_age is None:
        return False
    if require_contribution and user.contribution_count < 1:
        return False
    return datetime.now(UTC) - user.messaging_account_age >= timedelta(hours=min_account_age_hours)


async def open_cycle(
    cluster_ids: list[UUID],
    db: AsyncSession,
) -> VotingCycle:
    settings = get_settings()
    now = datetime.now(UTC)
    cycle = await create_voting_cycle(
        db,
        VotingCycleCreate(
            started_at=now,
            ends_at=now + timedelta(hours=settings.voting_cycle_hours),
            status="active",
            cluster_ids=cluster_ids,
            total_voters=0,
        ),
    )
    await append_evidence(
        session=db,
        event_type="cycle_opened",
        entity_type="voting_cycle",
        entity_id=cycle.id,
        payload={
            "cycle_id": str(cycle.id),
            "cluster_ids": [str(c) for c in cluster_ids],
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(hours=settings.voting_cycle_hours)).isoformat(),
            "cycle_duration_hours": settings.voting_cycle_hours,
        },
    )
    await db.commit()
    return cycle


_REMINDER_MESSAGES: dict[str, str] = {
    "fa": "⏰ یادآوری: رای‌گیری هنوز باز است!",
    "en": "⏰ Reminder: voting is still open!",
}

_REMINDER_BUTTON: dict[str, str] = {
    "fa": "🗳️ مشاهده رای‌گیری",
    "en": "🗳️ View ballot",
}


async def record_endorsement(
    *,
    session: AsyncSession,
    user: User,
    cluster_id: UUID,
) -> tuple[bool, str]:
    if not eligible_for_submission_or_endorsement(user):
        return False, "not_eligible"

    try:
        await create_policy_endorsement(
            session, PolicyEndorsementCreate(user_id=user.id, cluster_id=cluster_id)
        )
        if user.contribution_count == 0:
            user.contribution_count = 1
        await append_evidence(
            session=session,
            event_type="policy_endorsed",
            entity_type="policy_endorsement",
            entity_id=cluster_id,
            payload={"user_id": str(user.id), "cluster_id": str(cluster_id)},
        )
        await session.commit()
        return True, "recorded"
    except IntegrityError:
        await session.rollback()
        return True, "already_endorsed"


async def cast_vote(
    *,
    session: AsyncSession,
    user: User,
    cycle: VotingCycle,
    approved_cluster_ids: list[UUID] | None = None,
    selections: list[dict[str, str]] | None = None,
    min_account_age_hours: int,
    require_contribution: bool = True,
) -> tuple[Vote | None, str]:
    if not eligible_for_vote(
        user,
        min_account_age_hours=min_account_age_hours,
        require_contribution=require_contribution,
    ):
        return None, "not_eligible"
    if not await can_change_vote(session=session, user_id=user.id, cycle_id=cycle.id):
        return None, "vote_change_limit_reached"

    effective_approved = approved_cluster_ids or []
    if selections and not approved_cluster_ids:
        effective_approved = [UUID(s["cluster_id"]) for s in selections if s.get("option_id")]

    vote = await create_vote(
        session,
        VoteCreate(
            user_id=user.id,
            cycle_id=cycle.id,
            approved_cluster_ids=effective_approved,
            selections=selections,
        ),
    )
    payload: dict[str, object] = {
        "user_id": str(user.id),
        "cycle_id": str(cycle.id),
        "approved_cluster_ids": [str(v) for v in effective_approved],
    }
    if selections:
        payload["selections"] = selections
    await append_evidence(
        session=session,
        event_type="vote_cast",
        entity_type="vote",
        entity_id=vote.id,
        payload=payload,
    )
    await session.commit()
    return vote, "recorded"


async def close_and_tally(*, session: AsyncSession, cycle: VotingCycle) -> VotingCycle:
    total_voters_result = await session.execute(select(Vote).where(Vote.cycle_id == cycle.id))
    votes = list(total_voters_result.scalars().all())
    cycle.total_voters = len(votes)

    results: list[dict[str, Any]] = []
    for cluster_id in cycle.cluster_ids:
        approvals = await count_votes_for_cluster(session, cycle.id, cluster_id)
        rate = approvals / cycle.total_voters if cycle.total_voters else 0.0
        cluster_result: dict[str, Any] = {
            "cluster_id": str(cluster_id),
            "approval_count": float(approvals),
            "approval_rate": float(rate),
        }

        option_counts: dict[str, int] = {}
        for vote in votes:
            if vote.selections:
                for sel in vote.selections:
                    if sel.get("cluster_id") == str(cluster_id) and sel.get("option_id"):
                        oid = sel["option_id"]
                        option_counts[oid] = option_counts.get(oid, 0) + 1
        if option_counts:
            cluster_result["option_counts"] = option_counts

        results.append(cluster_result)

    cycle.results = results
    cycle.status = "tallied"
    await append_evidence(
        session=session,
        event_type="cycle_closed",
        entity_type="voting_cycle",
        entity_id=cycle.id,
        payload={"total_voters": cycle.total_voters, "results": results},
    )
    await session.commit()
    return cycle


async def send_reminder(
    cycle: VotingCycle,
    channel: BaseChannel,
    db: AsyncSession,
) -> int:
    """Send reminder to all verified users who haven't voted yet."""
    voted_result = await db.execute(select(Vote.user_id).where(Vote.cycle_id == cycle.id))
    voted_user_ids = {row[0] for row in voted_result.all()}

    all_users_result = await db.execute(
        select(User).where(User.email_verified.is_(True), User.messaging_verified.is_(True))
    )
    all_users = list(all_users_result.scalars().all())

    sent = 0
    for user in all_users:
        if user.id not in voted_user_ids and user.messaging_account_ref:
            locale = user.locale if user.locale in _REMINDER_MESSAGES else "en"
            reminder_text = _REMINDER_MESSAGES[locale]
            btn_text = _REMINDER_BUTTON.get(locale, _REMINDER_BUTTON["en"])
            keyboard = {"inline_keyboard": [[{"text": btn_text, "callback_data": "vote"}]]}
            success = await channel.send_message(
                OutboundMessage(
                    recipient_ref=user.messaging_account_ref,
                    text=reminder_text,
                    reply_markup=keyboard,
                )
            )
            if success:
                sent += 1
    return sent
