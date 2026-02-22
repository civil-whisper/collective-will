from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.evidence import append_evidence
from src.db.queries import create_user, get_user_by_email
from src.handlers.abuse import check_signup_limits
from src.models.user import User, UserCreate

_PENDING_MAGIC_LINKS: dict[str, tuple[str, datetime]] = {}
_PENDING_LINKING_CODES: dict[str, tuple[str, datetime]] = {}  # code -> (email, issued_at)
_FAILED_VERIFICATIONS: dict[str, list[datetime]] = {}

MAGIC_LINK_EXPIRY_MINUTES = 15
LINKING_CODE_EXPIRY_MINUTES = 60


def create_magic_link_token() -> str:
    return secrets.token_urlsafe(32)


def create_linking_code() -> str:
    return secrets.token_urlsafe(8)


async def subscribe_email(
    *,
    session: AsyncSession,
    email: str,
    locale: str,
    requester_ip: str,
    messaging_account_ref: str = "",
) -> tuple[User | None, str | None]:
    allowed, reason = await check_signup_limits(session=session, email=email, requester_ip=requester_ip)
    if not allowed:
        return None, reason

    existing = await get_user_by_email(session, email)
    if existing is not None:
        token = create_magic_link_token()
        _PENDING_MAGIC_LINKS[token] = (email, datetime.now(UTC))
        return existing, token

    user = await create_user(
        session,
        UserCreate(email=email, locale=locale, messaging_account_ref=messaging_account_ref),
    )
    token = create_magic_link_token()
    _PENDING_MAGIC_LINKS[token] = (email, datetime.now(UTC))

    settings = get_settings()
    magic_link = f"{settings.app_public_base_url}/verify?token={token}"
    import logging

    logging.getLogger(__name__).info("Magic link for %s: %s", email, magic_link)

    await session.commit()
    return user, token


def _is_locked(email: str) -> bool:
    attempts = _FAILED_VERIFICATIONS.get(email, [])
    now = datetime.now(UTC)
    recent = [a for a in attempts if now - a <= timedelta(hours=24)]
    _FAILED_VERIFICATIONS[email] = recent
    return len(recent) >= 5


async def verify_magic_link(*, session: AsyncSession, token: str) -> tuple[bool, str]:
    details = _PENDING_MAGIC_LINKS.get(token)
    if details is None:
        return False, "invalid_token"

    email, issued_at = details

    if _is_locked(email):
        return False, "locked_out"

    if datetime.now(UTC) - issued_at > timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES):
        _FAILED_VERIFICATIONS.setdefault(email, []).append(datetime.now(UTC))
        return False, "expired_token"

    user = await get_user_by_email(session, email)
    if user is None:
        return False, "user_not_found"

    user.email_verified = True
    user.last_active_at = datetime.now(UTC)

    linking_code = create_linking_code()
    _PENDING_LINKING_CODES[linking_code] = (email, datetime.now(UTC))

    await append_evidence(
        session=session,
        event_type="user_verified",
        entity_type="user",
        entity_id=user.id,
        payload={"method": "email_magic_link"},
    )
    await session.commit()
    _PENDING_MAGIC_LINKS.pop(token, None)
    return True, linking_code


async def resolve_linking_code(*, session: AsyncSession, code: str, account_ref: str) -> tuple[bool, str]:
    """Resolve a linking code sent by a user via WhatsApp to link their account."""
    details = _PENDING_LINKING_CODES.get(code)
    if details is None:
        return False, "invalid_code"

    email, issued_at = details
    if datetime.now(UTC) - issued_at > timedelta(minutes=LINKING_CODE_EXPIRY_MINUTES):
        _PENDING_LINKING_CODES.pop(code, None)
        return False, "expired_code"

    user = await get_user_by_email(session, email)
    if user is None:
        return False, "user_not_found"

    user.messaging_account_ref = account_ref
    user.messaging_verified = True
    user.messaging_account_age = datetime.now(UTC)

    await append_evidence(
        session=session,
        event_type="user_verified",
        entity_type="user",
        entity_id=user.id,
        payload={"method": "whatsapp_linked", "account_ref": account_ref},
    )
    await session.commit()
    _PENDING_LINKING_CODES.pop(code, None)
    return True, "linked"


async def link_whatsapp_account(
    *,
    session: AsyncSession,
    user: User,
    messaging_account_ref: str,
) -> User:
    user.messaging_account_ref = messaging_account_ref
    user.messaging_verified = True
    user.messaging_account_age = datetime.now(UTC)

    await append_evidence(
        session=session,
        event_type="user_verified",
        entity_type="user",
        entity_id=user.id,
        payload={"method": "whatsapp_linked", "account_ref": messaging_account_ref},
    )
    await session.commit()
    await session.refresh(user)
    return user
