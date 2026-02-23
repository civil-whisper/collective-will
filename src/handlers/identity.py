from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.evidence import append_evidence
from src.db.queries import create_user, get_user_by_email, get_user_by_messaging_ref
from src.db.verification_tokens import consume_token, lookup_token, store_token
from src.email.sender import send_magic_link_email
from src.handlers.abuse import check_signup_limits
from src.models.user import User, UserCreate
from src.security.web_auth import create_web_access_token

logger = logging.getLogger(__name__)


def create_magic_link_token() -> str:
    return secrets.token_urlsafe(32)


def create_linking_code() -> str:
    return secrets.token_urlsafe(8)


def create_web_session_code() -> str:
    return secrets.token_urlsafe(24)


async def subscribe_email(
    *,
    session: AsyncSession,
    email: str,
    locale: str,
    requester_ip: str,
    messaging_account_ref: str = "",
) -> tuple[User | None, str | None]:
    settings = get_settings()
    allowed, reason = await check_signup_limits(session=session, email=email, requester_ip=requester_ip)
    if not allowed:
        return None, reason

    existing = await get_user_by_email(session, email)
    if existing is not None:
        user = existing
    else:
        user = await create_user(
            session,
            UserCreate(email=email, locale=locale, messaging_account_ref=messaging_account_ref),
        )

    token = create_magic_link_token()
    await store_token(
        session,
        token=token,
        email=email,
        token_type="magic_link",
        expiry_minutes=settings.magic_link_expiry_minutes,
    )
    link_locale = locale if locale in ("en", "fa") else "en"
    magic_link = f"{settings.app_public_base_url}/{link_locale}/verify?token={token}"

    sent = await send_magic_link_email(
        to=email,
        magic_link_url=magic_link,
        locale=locale,
        resend_api_key=settings.resend_api_key,
        email_from=settings.email_from,
        expiry_minutes=settings.magic_link_expiry_minutes,
        http_timeout_seconds=settings.email_http_timeout_seconds,
    )
    if not sent:
        logger.warning("Failed to send magic link email to %s; token still valid", email)

    await session.commit()
    return user, token


async def verify_magic_link(
    *,
    session: AsyncSession,
    token: str,
) -> tuple[bool, str, str | None, str | None]:
    settings = get_settings()
    details = await lookup_token(session, token, "magic_link")
    if details is None:
        return False, "invalid_token", None, None

    email, is_expired = details

    if is_expired:
        await consume_token(session, token, "magic_link")
        await session.commit()
        return False, "expired_token", None, None

    user = await get_user_by_email(session, email)
    if user is None:
        return False, "user_not_found", None, None

    user.email_verified = True
    user.last_active_at = datetime.now(UTC)

    linking_code = create_linking_code()
    await store_token(
        session,
        token=linking_code,
        email=email,
        token_type="linking_code",
        expiry_minutes=settings.linking_code_expiry_minutes,
    )
    web_session_code = create_web_session_code()
    await store_token(
        session,
        token=web_session_code,
        email=email,
        token_type="web_session",
        expiry_minutes=settings.web_session_code_expiry_minutes,
    )

    await consume_token(session, token, "magic_link")

    await append_evidence(
        session=session,
        event_type="user_verified",
        entity_type="user",
        entity_id=user.id,
        payload={"method": "email_magic_link"},
    )
    await session.commit()
    return True, linking_code, email, web_session_code


async def exchange_web_session_code(
    *,
    session: AsyncSession,
    email: str,
    code: str,
) -> tuple[bool, str]:
    details = await lookup_token(session, code, "web_session")
    if details is None:
        return False, "invalid_code"

    token_email, is_expired = details
    if is_expired:
        await consume_token(session, code, "web_session")
        await session.commit()
        return False, "expired_code"

    if token_email != email:
        return False, "invalid_code"

    user = await get_user_by_email(session, token_email)
    if user is None or not user.email_verified:
        return False, "user_not_found"

    user.last_active_at = datetime.now(UTC)
    await consume_token(session, code, "web_session")
    await session.commit()

    access_token = create_web_access_token(email=token_email)
    return True, access_token


async def resolve_linking_code(*, session: AsyncSession, code: str, account_ref: str) -> tuple[bool, str]:
    """Resolve a linking code sent by a user via messaging to link their account."""
    details = await lookup_token(session, code, "linking_code")
    if details is None:
        return False, "invalid_code"

    email, is_expired = details

    if is_expired:
        await consume_token(session, code, "linking_code")
        await session.commit()
        return False, "expired_code"

    user = await get_user_by_email(session, email)
    if user is None:
        return False, "user_not_found"

    if user.messaging_verified:
        await consume_token(session, code, "linking_code")
        await session.commit()
        return False, "user_already_linked"

    existing_holder = await get_user_by_messaging_ref(session, account_ref)
    if existing_holder is not None and existing_holder.id != user.id:
        await consume_token(session, code, "linking_code")
        await session.commit()
        return False, "account_already_linked"

    user.messaging_account_ref = account_ref
    user.messaging_verified = True
    user.messaging_account_age = datetime.now(UTC)

    await consume_token(session, code, "linking_code")

    await append_evidence(
        session=session,
        event_type="user_verified",
        entity_type="user",
        entity_id=user.id,
        payload={"method": "messaging_linked", "account_ref": account_ref},
    )
    await session.commit()
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
