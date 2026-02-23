from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.models.submission import Submission
from src.models.user import User
from src.models.vote import Vote

logger = logging.getLogger(__name__)

KNOWN_DISPOSABLE_DOMAINS = {"mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email", "yopmail.com"}

_IP_SIGNUP_COUNTER: dict[str, list[datetime]] = {}
_IP_DOMAIN_TRACKER: dict[str, set[str]] = {}


class RateLimitResult(BaseModel):
    allowed: bool
    reason: str | None = None
    quarantine: bool = False


def is_major_provider(domain: str, settings: Settings | None = None) -> bool:
    active_settings = settings or get_settings()
    return domain.lower() in active_settings.major_email_provider_list()


async def check_submission_rate(db: AsyncSession, user_id: UUID) -> RateLimitResult:
    settings = get_settings()
    start = datetime.now(UTC) - timedelta(hours=24)
    result = await db.execute(
        select(func.count(Submission.id)).where(Submission.user_id == user_id, Submission.created_at >= start)
    )
    count = int(result.scalar_one())
    if count >= settings.max_submissions_per_day:
        return RateLimitResult(allowed=False, reason="submission_daily_limit")
    return RateLimitResult(allowed=True)


async def check_domain_rate(db: AsyncSession, email_domain: str) -> RateLimitResult:
    settings = get_settings()
    if is_major_provider(email_domain, settings):
        return RateLimitResult(allowed=True)
    start = datetime.now(UTC) - timedelta(days=1)
    result = await db.execute(
        select(func.count(User.id)).where(User.email.ilike(f"%@{email_domain}"), User.created_at >= start)
    )
    count = int(result.scalar_one())
    if count >= settings.max_signups_per_domain_per_day:
        return RateLimitResult(allowed=False, reason="domain_daily_limit")
    return RateLimitResult(allowed=True)


async def check_signup_ip_rate(db: AsyncSession, requester_ip: str) -> RateLimitResult:
    settings = get_settings()
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=1)
    entries = _IP_SIGNUP_COUNTER.get(requester_ip, [])
    recent = [ts for ts in entries if ts >= cutoff]
    _IP_SIGNUP_COUNTER[requester_ip] = recent
    if len(recent) >= settings.max_signups_per_ip_per_day:
        return RateLimitResult(allowed=False, reason="ip_daily_limit")
    return RateLimitResult(allowed=True)


async def check_signup_domain_diversity_by_ip(db: AsyncSession, requester_ip: str) -> RateLimitResult:
    """Track and flag anomalous distinct email-domain count from one IP. v0: flag only, no block."""
    settings = get_settings()
    domains = _IP_DOMAIN_TRACKER.get(requester_ip, set())
    if len(domains) >= settings.signup_domain_diversity_threshold:
        logger.warning("High domain diversity from IP %s: %d domains", requester_ip, len(domains))
        return RateLimitResult(allowed=True, reason="high_domain_diversity_flagged")
    return RateLimitResult(allowed=True)


async def score_disposable_email_domain(email_domain: str) -> float:
    """Return trust-score adjustment for disposable domains (soft signal only)."""
    if email_domain.lower() in KNOWN_DISPOSABLE_DOMAINS:
        return -0.5
    return 0.0


async def check_burst(db: AsyncSession, user_id: UUID) -> RateLimitResult:
    settings = get_settings()
    since = datetime.now(UTC) - timedelta(minutes=settings.burst_quarantine_window_minutes)
    result = await db.execute(
        select(func.count(Submission.id)).where(Submission.user_id == user_id, Submission.created_at >= since)
    )
    count = int(result.scalar_one())
    if count >= settings.burst_quarantine_threshold_count:
        return RateLimitResult(allowed=False, reason="burst_quarantine", quarantine=True)
    return RateLimitResult(allowed=True)


async def check_vote_change(db: AsyncSession, user_id: UUID, cycle_id: UUID) -> RateLimitResult:
    settings = get_settings()
    result = await db.execute(
        select(func.count(Vote.id)).where(Vote.user_id == user_id, Vote.cycle_id == cycle_id)
    )
    count = int(result.scalar_one())
    if count >= settings.max_vote_submissions_per_cycle:
        return RateLimitResult(allowed=False, reason="vote_change_limit")
    return RateLimitResult(allowed=True)


async def record_account_creation_velocity(
    db: AsyncSession,
    requester_ip: str | None,
    email_domain: str,
) -> None:
    """Emit account-creation velocity metrics for abuse monitoring."""
    if requester_ip:
        _IP_SIGNUP_COUNTER.setdefault(requester_ip, []).append(datetime.now(UTC))
        _IP_DOMAIN_TRACKER.setdefault(requester_ip, set()).add(email_domain)
    logger.info("Account creation velocity: ip=%s domain=%s", requester_ip, email_domain)


# Legacy wrappers for backward compatibility with existing handlers
async def check_signup_limits(*, session: AsyncSession, email: str, requester_ip: str) -> tuple[bool, str | None]:
    domain = email.split("@")[-1].lower()
    domain_result = await check_domain_rate(session, domain)
    if not domain_result.allowed:
        return False, domain_result.reason
    ip_result = await check_signup_ip_rate(session, requester_ip)
    if not ip_result.allowed:
        return False, ip_result.reason
    await record_account_creation_velocity(session, requester_ip, domain)
    return True, None


async def check_submission_rate_limit(*, session: AsyncSession, user_id: UUID) -> tuple[bool, str | None]:
    result = await check_submission_rate(session, user_id)
    return result.allowed, result.reason


async def check_burst_quarantine(*, session: AsyncSession, user_id: UUID) -> bool:
    result = await check_burst(session, user_id)
    return result.quarantine


async def can_change_vote(*, session: AsyncSession, user_id: UUID, cycle_id: UUID) -> bool:
    result = await check_vote_change(session, user_id, cycle_id)
    return result.allowed
