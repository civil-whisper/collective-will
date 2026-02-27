from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.db.ip_signup_log import IPSignupLog
from src.handlers.abuse import (
    RateLimitResult,
    check_burst,
    check_domain_rate,
    check_signup_domain_diversity_by_ip,
    check_signup_ip_rate,
    check_submission_rate,
    check_vote_change,
    is_major_provider,
    record_account_creation_velocity,
    score_disposable_email_domain,
)


def test_rate_limit_result_fields() -> None:
    r = RateLimitResult(allowed=True)
    assert r.allowed is True
    assert r.reason is None
    assert r.quarantine is False

    r2 = RateLimitResult(allowed=False, reason="test", quarantine=True)
    assert r2.allowed is False
    assert r2.reason == "test"
    assert r2.quarantine is True


@pytest.mark.asyncio
async def test_check_submission_rate_allows_5(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 4
    db.execute.return_value = scalar_mock

    result = await check_submission_rate(db, uuid4())
    assert result.allowed is True


@pytest.mark.asyncio
async def test_check_submission_rate_denies_6th(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 5
    db.execute.return_value = scalar_mock

    result = await check_submission_rate(db, uuid4())
    assert result.allowed is False
    assert result.reason == "submission_daily_limit"


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_domain_rate_allows_3(mock_settings: MagicMock) -> None:
    mock_settings.return_value.max_signups_per_domain_per_day = 3
    mock_settings.return_value.major_email_provider_list.return_value = {"gmail.com", "yahoo.com"}

    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 2
    db.execute.return_value = scalar_mock

    result = await check_domain_rate(db, "rare-domain.com")
    assert result.allowed is True


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_domain_rate_denies_4th(mock_settings: MagicMock) -> None:
    mock_settings.return_value.max_signups_per_domain_per_day = 3
    mock_settings.return_value.major_email_provider_list.return_value = {"gmail.com", "yahoo.com"}

    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 3
    db.execute.return_value = scalar_mock

    result = await check_domain_rate(db, "rare-domain.com")
    assert result.allowed is False
    assert result.reason == "domain_daily_limit"


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_domain_rate_major_exempt(mock_settings: MagicMock) -> None:
    mock_settings.return_value.major_email_provider_list.return_value = {"gmail.com"}

    db = AsyncMock()
    result = await check_domain_rate(db, "gmail.com")
    assert result.allowed is True


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_signup_ip_rate_allows_up_to_cap(mock_settings: MagicMock) -> None:
    mock_settings.return_value.max_signups_per_ip_per_day = 10
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 9
    db.execute.return_value = scalar_mock
    result = await check_signup_ip_rate(db, "1.2.3.4")
    assert result.allowed is True


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_signup_ip_rate_denies_above_cap(mock_settings: MagicMock) -> None:
    mock_settings.return_value.max_signups_per_ip_per_day = 2
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 2
    db.execute.return_value = scalar_mock
    result = await check_signup_ip_rate(db, "1.2.3.4")
    assert result.allowed is False
    assert result.reason == "ip_daily_limit"


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_domain_diversity_flags_high_count(mock_settings: MagicMock) -> None:
    mock_settings.return_value.signup_domain_diversity_threshold = 5
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 5
    db.execute.return_value = scalar_mock
    result = await check_signup_domain_diversity_by_ip(db, "1.2.3.4")
    assert result.allowed is True
    assert result.reason == "high_domain_diversity_flagged"


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_domain_diversity_normal(mock_settings: MagicMock) -> None:
    mock_settings.return_value.signup_domain_diversity_threshold = 5
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 1
    db.execute.return_value = scalar_mock
    result = await check_signup_domain_diversity_by_ip(db, "1.2.3.4")
    assert result.allowed is True
    assert result.reason is None


@pytest.mark.asyncio
async def test_score_disposable_domain() -> None:
    score = await score_disposable_email_domain("mailinator.com")
    assert score < 0.0

    clean_score = await score_disposable_email_domain("example.com")
    assert clean_score == 0.0


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_burst_triggers(mock_settings: MagicMock) -> None:
    mock_settings.return_value.burst_quarantine_threshold_count = 3
    mock_settings.return_value.burst_quarantine_window_minutes = 5

    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 3
    db.execute.return_value = scalar_mock

    result = await check_burst(db, uuid4())
    assert result.quarantine is True
    assert result.allowed is False


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_burst_does_not_trigger(mock_settings: MagicMock) -> None:
    mock_settings.return_value.burst_quarantine_threshold_count = 3
    mock_settings.return_value.burst_quarantine_window_minutes = 5

    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 2
    db.execute.return_value = scalar_mock

    result = await check_burst(db, uuid4())
    assert result.quarantine is False
    assert result.allowed is True


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_vote_change_first_allowed(mock_settings: MagicMock) -> None:
    mock_settings.return_value.max_vote_submissions_per_cycle = 2
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 1
    db.execute.return_value = scalar_mock

    result = await check_vote_change(db, uuid4(), uuid4())
    assert result.allowed is True


@pytest.mark.asyncio
@patch("src.handlers.abuse.get_settings")
async def test_check_vote_change_second_denied(mock_settings: MagicMock) -> None:
    mock_settings.return_value.max_vote_submissions_per_cycle = 2
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 2
    db.execute.return_value = scalar_mock

    result = await check_vote_change(db, uuid4(), uuid4())
    assert result.allowed is False
    assert result.reason == "vote_change_limit"


@pytest.mark.asyncio
async def test_record_velocity_tracks() -> None:
    db = AsyncMock()
    await record_account_creation_velocity(db, "1.2.3.4", "example.com")
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert isinstance(added, IPSignupLog)
    assert added.requester_ip == "1.2.3.4"
    assert added.email_domain == "example.com"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_db_submission_rate() -> None:
    db = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 0
    db.execute.return_value = scalar_mock

    result = await check_submission_rate(db, uuid4())
    assert result.allowed is True


@patch("src.handlers.abuse.get_settings")
def test_is_major_provider(mock_settings: MagicMock) -> None:
    mock_settings.return_value.major_email_provider_list.return_value = {"gmail.com", "yahoo.com"}
    assert is_major_provider("gmail.com") is True
    assert is_major_provider("rare-domain.org") is False
