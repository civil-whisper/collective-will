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
    NOT_ELIGIBLE_FA,
    PII_WARNING_FA,
    RATE_LIMIT_FA,
    detect_high_risk_pii,
    eligible_for_submission,
    handle_submission,
    hash_submission,
)
from src.models.submission import PolicyCandidateCreate
from src.pipeline.canonicalize import CanonicalizationRejection


class FakeChannel(BaseChannel):
    def __init__(self) -> None:
        self.sent: list[OutboundMessage] = []

    async def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        return None

    async def send_message(self, message: OutboundMessage) -> bool:
        self.sent.append(message)
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


def _make_candidate_create(submission_id: Any = None) -> PolicyCandidateCreate:
    return PolicyCandidateCreate(
        submission_id=submission_id or uuid4(),
        title="Clean Water Policy",
        summary="A proposal about clean drinking water",
        stance="support",
        policy_topic="water-access",
        policy_key="clean-drinking-water",
        entities=["water"],
        confidence=0.95,
        ambiguity_flags=[],
        model_version="test-model",
        prompt_version="test-prompt",
    )


@pytest.mark.asyncio
@patch("src.handlers.intake.check_submission_rate_limit", new_callable=AsyncMock, return_value=(True, None))
@patch("src.handlers.intake.check_burst_quarantine", new_callable=AsyncMock, return_value=False)
@patch("src.handlers.intake.create_submission", new_callable=AsyncMock)
@patch("src.handlers.intake.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.intake.canonicalize_single", new_callable=AsyncMock)
@patch("src.handlers.intake.create_policy_candidate", new_callable=AsyncMock)
@patch("src.handlers.intake.compute_and_store_embeddings", new_callable=AsyncMock)
@patch("src.handlers.intake.get_settings")
async def test_handle_submission_verified_user(
    mock_settings: MagicMock,
    mock_embed: AsyncMock,
    mock_create_candidate: AsyncMock,
    mock_canon: AsyncMock,
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

    candidate_create = _make_candidate_create(sub.id)
    mock_canon.return_value = candidate_create
    mock_create_candidate.return_value = MagicMock()

    channel = FakeChannel()
    user = _make_user()
    db = AsyncMock()
    msg = _make_msg("مشکل آب آشامیدنی")

    await handle_submission(msg, user, channel, db)

    mock_create.assert_called_once()
    mock_canon.assert_called_once()
    mock_create_candidate.assert_called_once()
    mock_embed.assert_called_once()
    assert sub.status == "canonicalized"
    assert user.contribution_count == 1
    assert len(channel.sent) == 1
    assert "Clean Water Policy" in channel.sent[0].text


@pytest.mark.asyncio
@patch("src.handlers.intake.check_submission_rate_limit", new_callable=AsyncMock, return_value=(True, None))
@patch("src.handlers.intake.check_burst_quarantine", new_callable=AsyncMock, return_value=False)
@patch("src.handlers.intake.create_submission", new_callable=AsyncMock)
@patch("src.handlers.intake.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.intake.canonicalize_single", new_callable=AsyncMock)
@patch("src.handlers.intake.get_settings")
async def test_handle_submission_garbage_rejected(
    mock_settings: MagicMock,
    mock_canon: AsyncMock,
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

    mock_canon.return_value = CanonicalizationRejection(
        reason="این یک سلام است، نه پیشنهاد سیاستی.",
        model_version="test-model",
        prompt_version="test-prompt",
    )

    channel = FakeChannel()
    user = _make_user()
    db = AsyncMock()

    await handle_submission(_make_msg("سلام!"), user, channel, db)

    assert sub.status == "rejected"
    assert user.contribution_count == 0
    assert len(channel.sent) == 1
    assert "این یک سلام است" in channel.sent[0].text


@pytest.mark.asyncio
@patch("src.handlers.intake.check_submission_rate_limit", new_callable=AsyncMock, return_value=(True, None))
@patch("src.handlers.intake.check_burst_quarantine", new_callable=AsyncMock, return_value=False)
@patch("src.handlers.intake.create_submission", new_callable=AsyncMock)
@patch("src.handlers.intake.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.intake.canonicalize_single", new_callable=AsyncMock)
@patch("src.handlers.intake.get_settings")
async def test_handle_submission_llm_failure_falls_back(
    mock_settings: MagicMock,
    mock_canon: AsyncMock,
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

    mock_canon.side_effect = RuntimeError("LLM service unavailable")

    channel = FakeChannel()
    user = _make_user()
    db = AsyncMock()

    await handle_submission(_make_msg("سیاست مهم"), user, channel, db)

    assert sub.status == "pending"
    assert user.contribution_count == 0
    assert len(channel.sent) == 1
    assert "دریافت شد" in channel.sent[0].text


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
