from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.handlers.intake import (
    CONFIRMATION_FA,
    NOT_ELIGIBLE_FA,
    PII_WARNING_FA,
    RATE_LIMIT_FA,
    detect_high_risk_pii,
    eligible_for_submission,
    handle_submission,
    hash_submission,
)


class FakeChannel(BaseChannel):
    def __init__(self) -> None:
        self.sent: list[OutboundMessage] = []

    def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        return None

    async def send_message(self, message: OutboundMessage) -> bool:
        self.sent.append(message)
        return True

    async def send_ballot(self, recipient_ref: str, policies: list[dict[str, Any]]) -> bool:
        return True


def _make_user(
    verified: bool = True,
    messaging_verified: bool = True,
    age_hours: int = 72,
    locale: str = "fa",
) -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.email_verified = verified
    user.messaging_verified = messaging_verified
    user.messaging_account_age = datetime.now(UTC) - timedelta(hours=age_hours) if age_hours >= 0 else None
    user.locale = locale
    user.contribution_count = 0
    return user


def _make_msg(text: str = "test text") -> UnifiedMessage:
    return UnifiedMessage(sender_ref="ref-1", text=text, message_id="m1")


def test_detect_pii_email() -> None:
    assert detect_high_risk_pii("contact me at test@example.com") is True


def test_detect_pii_phone() -> None:
    assert detect_high_risk_pii("call 09123456789 now") is True


def test_detect_pii_clean() -> None:
    assert detect_high_risk_pii("مشکل آب آشامیدنی") is False


def test_hash_submission_sha256() -> None:
    text = "test content"
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert hash_submission(text) == expected


def test_eligible_verified_user() -> None:
    user = _make_user()
    assert eligible_for_submission(user, min_account_age_hours=48) is True


def test_ineligible_email_not_verified() -> None:
    user = _make_user(verified=False)
    assert eligible_for_submission(user, min_account_age_hours=48) is False


def test_ineligible_messaging_not_verified() -> None:
    user = _make_user(messaging_verified=False)
    assert eligible_for_submission(user, min_account_age_hours=48) is False


def test_ineligible_account_too_young() -> None:
    user = _make_user(age_hours=1)
    assert eligible_for_submission(user, min_account_age_hours=48) is False


def test_eligible_with_low_age_config() -> None:
    user = _make_user(age_hours=2)
    assert eligible_for_submission(user, min_account_age_hours=1) is True


@pytest.mark.asyncio
@patch("src.handlers.intake.check_submission_rate_limit", new_callable=AsyncMock, return_value=(True, None))
@patch("src.handlers.intake.check_burst_quarantine", new_callable=AsyncMock, return_value=False)
@patch("src.handlers.intake.create_submission", new_callable=AsyncMock)
@patch("src.handlers.intake.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.intake.get_settings")
async def test_handle_submission_verified_user(
    mock_settings: MagicMock,
    mock_evidence: AsyncMock,
    mock_create: AsyncMock,
    mock_burst: AsyncMock,
    mock_rate: AsyncMock,
) -> None:
    mock_settings.return_value.min_account_age_hours = 48
    sub = MagicMock()
    sub.id = uuid4()
    sub.status = "pending"
    mock_create.return_value = sub

    channel = FakeChannel()
    user = _make_user()
    db = AsyncMock()
    msg = _make_msg("مشکل آب آشامیدنی")

    await handle_submission(msg, user, channel, db)

    assert any(CONFIRMATION_FA in m.text for m in channel.sent)
    mock_create.assert_called_once()
    mock_evidence.assert_called()
    assert user.contribution_count == 0


@pytest.mark.asyncio
async def test_handle_submission_unverified_email() -> None:
    channel = FakeChannel()
    user = _make_user(verified=False)
    db = AsyncMock()

    with patch("src.handlers.intake.get_settings") as mock_settings:
        mock_settings.return_value.min_account_age_hours = 48
        await handle_submission(_make_msg(), user, channel, db)

    assert any(NOT_ELIGIBLE_FA in m.text for m in channel.sent)


@pytest.mark.asyncio
async def test_handle_submission_unverified_messaging() -> None:
    channel = FakeChannel()
    user = _make_user(messaging_verified=False)
    db = AsyncMock()

    with patch("src.handlers.intake.get_settings") as mock_settings:
        mock_settings.return_value.min_account_age_hours = 48
        await handle_submission(_make_msg(), user, channel, db)

    assert any(NOT_ELIGIBLE_FA in m.text for m in channel.sent)


@pytest.mark.asyncio
@patch(
    "src.handlers.intake.check_submission_rate_limit",
    new_callable=AsyncMock,
    return_value=(False, "submission_daily_limit"),
)
@patch("src.handlers.intake.get_settings")
async def test_handle_submission_rate_limited(mock_settings: MagicMock, mock_rate: AsyncMock) -> None:
    mock_settings.return_value.min_account_age_hours = 48
    channel = FakeChannel()
    user = _make_user()
    db = AsyncMock()

    await handle_submission(_make_msg(), user, channel, db)
    assert any(RATE_LIMIT_FA in m.text for m in channel.sent)


@pytest.mark.asyncio
@patch("src.handlers.intake.check_submission_rate_limit", new_callable=AsyncMock, return_value=(True, None))
@patch("src.handlers.intake.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.intake.get_settings")
async def test_handle_submission_pii_detected(
    mock_settings: MagicMock, mock_evidence: AsyncMock, mock_rate: AsyncMock,
) -> None:
    mock_settings.return_value.min_account_age_hours = 48
    channel = FakeChannel()
    user = _make_user()
    db = AsyncMock()

    await handle_submission(_make_msg("email test@example.com"), user, channel, db)
    assert any(PII_WARNING_FA in m.text for m in channel.sent)
    mock_evidence.assert_called_once()
    call_kwargs = mock_evidence.call_args.kwargs
    assert "raw_text" not in str(call_kwargs.get("payload", {})) or "test@example.com" not in str(
        call_kwargs.get("payload", {})
    )
