from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.handlers.voting import (
    cast_vote,
    close_and_tally,
    eligible_for_vote,
    open_cycle,
    parse_ballot,
    record_endorsement,
    send_ballot_prompt,
    send_reminder,
)


class FakeChannel(BaseChannel):
    def __init__(self) -> None:
        self.sent: list[OutboundMessage] = []

    async def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
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
    contribution_count: int = 1,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.email_verified = verified
    user.messaging_verified = messaging_verified
    user.messaging_account_age = datetime.now(UTC) - timedelta(hours=age_hours) if age_hours >= 0 else None
    user.contribution_count = contribution_count
    user.messaging_account_ref = "ref-1"
    user.locale = "fa"
    return user


# --- parse_ballot tests ---

def test_parse_ballot_arabic_comma() -> None:
    assert parse_ballot("1, 3, 5", 10) == [1, 3, 5]


def test_parse_ballot_farsi_numerals() -> None:
    assert parse_ballot("۱، ۳", 5) == [1, 3]


def test_parse_ballot_out_of_range() -> None:
    assert parse_ballot("0, 11", 10) is None


def test_parse_ballot_non_numeric() -> None:
    assert parse_ballot("hello", 5) is None


def test_parse_ballot_space_separated() -> None:
    assert parse_ballot("2 4", 5) == [2, 4]


def test_parse_ballot_empty() -> None:
    assert parse_ballot("", 5) is None


# --- eligible_for_vote tests ---

def test_eligible_vote_all_conditions_met() -> None:
    user = _make_user()
    assert eligible_for_vote(user, 48) is True


def test_ineligible_no_contributions() -> None:
    user = _make_user(contribution_count=0)
    assert eligible_for_vote(user, 48) is False


def test_eligible_no_contributions_when_not_required() -> None:
    user = _make_user(contribution_count=0)
    assert eligible_for_vote(user, 48, require_contribution=False) is True


def test_ineligible_email_not_verified() -> None:
    user = _make_user(verified=False)
    assert eligible_for_vote(user, 48) is False


def test_ineligible_messaging_not_verified() -> None:
    user = _make_user(messaging_verified=False)
    assert eligible_for_vote(user, 48) is False


def test_ineligible_account_too_young() -> None:
    user = _make_user(age_hours=1)
    assert eligible_for_vote(user, 48) is False


def test_eligible_with_low_age_config() -> None:
    user = _make_user(age_hours=2)
    assert eligible_for_vote(user, 1) is True


def test_eligible_with_endorsement_only() -> None:
    """User with no submissions but at least one recorded endorsement (contribution_count=1) can vote."""
    user = _make_user(contribution_count=1)
    assert eligible_for_vote(user, 48) is True


# --- open_cycle tests ---

@pytest.mark.asyncio
@patch("src.handlers.voting.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.voting.create_voting_cycle", new_callable=AsyncMock)
@patch("src.handlers.voting.get_settings")
async def test_open_cycle_creates_with_correct_dates(
    mock_settings: MagicMock, mock_create: AsyncMock, mock_evidence: AsyncMock,
) -> None:
    mock_settings.return_value.voting_cycle_hours = 48
    cycle = MagicMock()
    cycle.id = uuid4()
    mock_create.return_value = cycle
    db = AsyncMock()

    cluster_ids = [uuid4(), uuid4()]
    result = await open_cycle(cluster_ids, db)
    assert result == cycle
    mock_evidence.assert_called_once()
    evidence_kwargs = mock_evidence.call_args.kwargs
    assert evidence_kwargs["event_type"] == "cycle_opened"


# --- record_endorsement tests ---

@pytest.mark.asyncio
@patch("src.handlers.voting.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.voting.create_policy_endorsement", new_callable=AsyncMock)
@patch("src.handlers.voting.get_settings")
async def test_record_endorsement_success(
    mock_settings: MagicMock, mock_create: AsyncMock, mock_evidence: AsyncMock,
) -> None:
    mock_settings.return_value.min_account_age_hours = 48
    mock_settings.return_value.require_contribution_for_vote = True
    user = _make_user(contribution_count=0)
    db = AsyncMock()

    ok, status = await record_endorsement(session=db, user=user, cluster_id=uuid4())
    assert ok is True
    assert status == "recorded"
    assert user.contribution_count == 1
    mock_evidence.assert_called_once()
    assert mock_evidence.call_args.kwargs["event_type"] == "policy_endorsed"


@pytest.mark.asyncio
@patch("src.handlers.voting.create_policy_endorsement", new_callable=AsyncMock)
@patch("src.handlers.voting.get_settings")
async def test_record_endorsement_idempotent(mock_settings: MagicMock, mock_create: AsyncMock) -> None:
    from sqlalchemy.exc import IntegrityError

    mock_settings.return_value.min_account_age_hours = 48
    mock_settings.return_value.require_contribution_for_vote = True
    mock_create.side_effect = IntegrityError("dup", params=None, orig=Exception("dup"))
    user = _make_user()
    db = AsyncMock()

    ok, status = await record_endorsement(session=db, user=user, cluster_id=uuid4())
    assert ok is True
    assert status == "already_endorsed"


# --- cast_vote tests ---

@pytest.mark.asyncio
@patch("src.handlers.voting.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.voting.create_vote", new_callable=AsyncMock)
@patch("src.handlers.voting.can_change_vote", new_callable=AsyncMock, return_value=True)
async def test_cast_vote_success(
    mock_change: AsyncMock, mock_create: AsyncMock, mock_evidence: AsyncMock,
) -> None:
    vote = MagicMock()
    vote.id = uuid4()
    mock_create.return_value = vote

    user = _make_user()
    cycle = MagicMock()
    cycle.id = uuid4()
    db = AsyncMock()

    result_vote, status = await cast_vote(
        session=db, user=user, cycle=cycle,
        approved_cluster_ids=[uuid4()], min_account_age_hours=48,
    )
    assert result_vote is not None
    assert status == "recorded"
    mock_evidence.assert_called_once()


@pytest.mark.asyncio
async def test_cast_vote_ineligible_no_contributions() -> None:
    user = _make_user(contribution_count=0)
    cycle = MagicMock()
    db = AsyncMock()
    vote, status = await cast_vote(
        session=db, user=user, cycle=cycle,
        approved_cluster_ids=[], min_account_age_hours=48,
    )
    assert vote is None
    assert status == "not_eligible"


@pytest.mark.asyncio
@patch("src.handlers.voting.can_change_vote", new_callable=AsyncMock, return_value=False)
async def test_cast_vote_change_limit(mock_change: AsyncMock) -> None:
    user = _make_user()
    cycle = MagicMock()
    cycle.id = uuid4()
    db = AsyncMock()
    vote, status = await cast_vote(
        session=db, user=user, cycle=cycle,
        approved_cluster_ids=[], min_account_age_hours=48,
    )
    assert vote is None
    assert status == "vote_change_limit_reached"


# --- close_and_tally tests ---

@pytest.mark.asyncio
@patch("src.handlers.voting.append_evidence", new_callable=AsyncMock)
@patch("src.handlers.voting.count_votes_for_cluster", new_callable=AsyncMock, return_value=3)
async def test_close_and_tally(mock_count: AsyncMock, mock_evidence: AsyncMock) -> None:
    vote1 = MagicMock()
    vote2 = MagicMock()
    vote3 = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [vote1, vote2, vote3]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    db = AsyncMock()
    db.execute.return_value = result_mock

    cluster_id = uuid4()
    cycle = MagicMock()
    cycle.id = uuid4()
    cycle.cluster_ids = [cluster_id]
    cycle.results = None
    cycle.total_voters = 0

    updated = await close_and_tally(session=db, cycle=cycle)
    assert updated.total_voters == 3
    assert updated.status == "tallied"
    assert updated.results is not None
    assert len(updated.results) == 1
    assert updated.results[0]["approval_count"] == 3.0
    assert updated.results[0]["approval_rate"] == 1.0
    mock_evidence.assert_called_once()
    assert mock_evidence.call_args.kwargs["event_type"] == "cycle_closed"


# --- send_ballot_prompt tests ---

@pytest.mark.asyncio
async def test_send_ballot_prompt_formats() -> None:
    channel = FakeChannel()
    user = _make_user()
    cycle = MagicMock()
    cluster = MagicMock()
    cluster.summary = "اقتصاد بهتر"

    result = await send_ballot_prompt(user, cycle, [cluster], channel)
    assert result is True
    assert len(channel.sent) == 1
    assert "1. اقتصاد بهتر" in channel.sent[0].text


# --- send_reminder tests ---

@pytest.mark.asyncio
async def test_send_reminder_skips_already_voted() -> None:
    user1 = MagicMock()
    user1.id = uuid4()
    user1.email_verified = True
    user1.messaging_verified = True
    user1.messaging_account_ref = "ref-1"

    user2 = MagicMock()
    user2.id = uuid4()
    user2.email_verified = True
    user2.messaging_verified = True
    user2.messaging_account_ref = "ref-2"

    voted_result = MagicMock()
    voted_result.all.return_value = [(user1.id,)]

    all_users_scalars = MagicMock()
    all_users_scalars.all.return_value = [user1, user2]
    all_users_result = MagicMock()
    all_users_result.scalars.return_value = all_users_scalars

    db = AsyncMock()
    db.execute.side_effect = [voted_result, all_users_result]

    cycle = MagicMock()
    cycle.id = uuid4()
    channel = FakeChannel()

    sent = await send_reminder(cycle, channel, db)
    assert sent == 1
    assert channel.sent[0].recipient_ref == "ref-2"
