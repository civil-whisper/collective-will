from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.handlers.identity import (
    LINKING_CODE_EXPIRY_MINUTES,
    MAGIC_LINK_EXPIRY_MINUTES,
    create_linking_code,
    create_magic_link_token,
    link_whatsapp_account,
    resolve_linking_code,
    subscribe_email,
    verify_magic_link,
)


def test_magic_link_token_uses_secrets() -> None:
    token = create_magic_link_token()
    assert len(token) > 20


def test_linking_code_uses_secrets() -> None:
    code = create_linking_code()
    assert len(code) > 5


def test_magic_link_expiry_is_15_minutes() -> None:
    assert MAGIC_LINK_EXPIRY_MINUTES == 15


def test_linking_code_expiry_is_60_minutes() -> None:
    assert LINKING_CODE_EXPIRY_MINUTES == 60


@pytest.mark.asyncio
@patch("src.handlers.identity.send_magic_link_email", new_callable=AsyncMock, return_value=True)
@patch("src.handlers.identity.store_token", new_callable=AsyncMock)
@patch("src.handlers.identity.check_signup_limits", new_callable=AsyncMock, return_value=(True, None))
@patch("src.handlers.identity.get_user_by_email", new_callable=AsyncMock, return_value=None)
@patch("src.handlers.identity.create_user", new_callable=AsyncMock)
@patch("src.handlers.identity.get_settings")
async def test_subscribe_creates_user(
    mock_settings: MagicMock,
    mock_create: AsyncMock,
    mock_get: AsyncMock,
    mock_limits: AsyncMock,
    mock_store: AsyncMock,
    mock_send_email: AsyncMock,
) -> None:
    mock_settings.return_value.app_public_base_url = "https://test.example.com"
    mock_settings.return_value.resend_api_key = None
    mock_settings.return_value.email_from = "test@resend.dev"
    new_user = MagicMock()
    new_user.id = uuid4()
    mock_create.return_value = new_user
    session = AsyncMock()

    user, token = await subscribe_email(
        session=session, email="test@example.com", locale="fa", requester_ip="1.2.3.4",
    )
    assert user is not None
    assert token is not None
    mock_create.assert_called_once()
    mock_store.assert_called_once()
    mock_send_email.assert_called_once()


@pytest.mark.asyncio
@patch("src.handlers.identity.check_signup_limits", new_callable=AsyncMock, return_value=(False, "domain_daily_limit"))
async def test_subscribe_blocked_by_rate_limit(mock_limits: AsyncMock) -> None:
    session = AsyncMock()
    user, reason = await subscribe_email(
        session=session, email="test@rare-domain.com", locale="fa", requester_ip="1.2.3.4",
    )
    assert user is None
    assert reason == "domain_daily_limit"


@pytest.mark.asyncio
@patch("src.handlers.identity.consume_token", new_callable=AsyncMock, return_value=True)
@patch("src.handlers.identity.store_token", new_callable=AsyncMock)
@patch("src.handlers.identity.lookup_token", new_callable=AsyncMock, return_value=("test@example.com", False))
@patch("src.handlers.identity.get_user_by_email", new_callable=AsyncMock)
@patch("src.handlers.identity.append_evidence", new_callable=AsyncMock)
async def test_verify_valid_token(
    mock_evidence: AsyncMock,
    mock_get: AsyncMock,
    mock_lookup: AsyncMock,
    mock_store: AsyncMock,
    mock_consume: AsyncMock,
) -> None:
    user = MagicMock()
    user.id = uuid4()
    user.email_verified = False
    mock_get.return_value = user
    session = AsyncMock()

    ok, linking_code = await verify_magic_link(session=session, token="tok123")
    assert ok is True
    assert user.email_verified is True
    mock_store.assert_called_once()
    mock_consume.assert_called()
    mock_evidence.assert_called_once()


@pytest.mark.asyncio
@patch("src.handlers.identity.consume_token", new_callable=AsyncMock, return_value=True)
@patch("src.handlers.identity.lookup_token", new_callable=AsyncMock, return_value=("test@example.com", True))
async def test_verify_expired_token(mock_lookup: AsyncMock, mock_consume: AsyncMock) -> None:
    session = AsyncMock()
    ok, status = await verify_magic_link(session=session, token="expired")
    assert ok is False
    assert status == "expired_token"


@pytest.mark.asyncio
@patch("src.handlers.identity.lookup_token", new_callable=AsyncMock, return_value=None)
async def test_verify_invalid_token(mock_lookup: AsyncMock) -> None:
    session = AsyncMock()
    ok, status = await verify_magic_link(session=session, token="nonexistent")
    assert ok is False
    assert status == "invalid_token"


@pytest.mark.asyncio
@patch("src.handlers.identity.consume_token", new_callable=AsyncMock, return_value=True)
@patch("src.handlers.identity.lookup_token", new_callable=AsyncMock, return_value=("test@example.com", False))
@patch("src.handlers.identity.get_user_by_email", new_callable=AsyncMock)
@patch("src.handlers.identity.append_evidence", new_callable=AsyncMock)
async def test_resolve_linking_code_valid(
    mock_evidence: AsyncMock,
    mock_get: AsyncMock,
    mock_lookup: AsyncMock,
    mock_consume: AsyncMock,
) -> None:
    user = MagicMock()
    user.id = uuid4()
    user.messaging_account_ref = ""
    user.messaging_verified = False
    mock_get.return_value = user
    session = AsyncMock()

    ok, status = await resolve_linking_code(session=session, code="code123", account_ref="opaque-ref")
    assert ok is True
    assert status == "linked"
    assert user.messaging_verified is True
    assert user.messaging_account_ref == "opaque-ref"
    mock_consume.assert_called()
    mock_evidence.assert_called_once()


@pytest.mark.asyncio
@patch("src.handlers.identity.consume_token", new_callable=AsyncMock, return_value=True)
@patch("src.handlers.identity.lookup_token", new_callable=AsyncMock, return_value=("test@example.com", True))
async def test_resolve_linking_code_expired(mock_lookup: AsyncMock, mock_consume: AsyncMock) -> None:
    session = AsyncMock()
    ok, status = await resolve_linking_code(session=session, code="old-code", account_ref="ref")
    assert ok is False
    assert status == "expired_code"


@pytest.mark.asyncio
@patch("src.handlers.identity.lookup_token", new_callable=AsyncMock, return_value=None)
async def test_resolve_linking_code_invalid(mock_lookup: AsyncMock) -> None:
    session = AsyncMock()
    ok, status = await resolve_linking_code(session=session, code="nope", account_ref="ref")
    assert ok is False
    assert status == "invalid_code"


@pytest.mark.asyncio
@patch("src.handlers.identity.append_evidence", new_callable=AsyncMock)
async def test_link_whatsapp_stores_opaque_ref(mock_evidence: AsyncMock) -> None:
    user = MagicMock()
    user.id = uuid4()
    user.messaging_account_ref = ""
    user.messaging_verified = False
    session = AsyncMock()

    result = await link_whatsapp_account(session=session, user=user, messaging_account_ref="opaque-ref-123")
    assert result.messaging_verified is True
    assert result.messaging_account_ref == "opaque-ref-123"
    mock_evidence.assert_called_once()
    evidence_payload = mock_evidence.call_args.kwargs.get("payload", {})
    assert evidence_payload.get("account_ref") == "opaque-ref-123"
