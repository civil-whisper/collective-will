from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.handlers.commands import (
    _MESSAGES,
    _WELCOME,
    REGISTER_HINT,
    route_message,
)


class FakeChannel(BaseChannel):
    def __init__(self) -> None:
        self.messages: list[OutboundMessage] = []
        self.answered_callbacks: list[str] = []
        self.edited_markups: list[tuple[str, str, dict[str, Any]]] = []

    async def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        return None

    async def send_message(self, message: OutboundMessage) -> bool:
        self.messages.append(message)
        return True

    async def answer_callback(self, callback_query_id: str, text: str | None = None) -> bool:
        self.answered_callbacks.append(callback_query_id)
        return True

    async def edit_message_markup(
        self, recipient_ref: str, message_id: str, reply_markup: dict[str, Any]
    ) -> bool:
        self.edited_markups.append((recipient_ref, message_id, reply_markup))
        return True


def _text_msg(text: str, sender_ref: str = "ref-1") -> UnifiedMessage:
    return UnifiedMessage(
        sender_ref=sender_ref, text=text, platform="telegram",
        message_id=f"test-{uuid4().hex[:8]}",
    )


def _callback_msg(
    data: str, sender_ref: str = "ref-1", message_id: str = "msg-100"
) -> UnifiedMessage:
    return UnifiedMessage(
        sender_ref=sender_ref, text="", platform="telegram",
        message_id=message_id,
        callback_data=data, callback_query_id=f"cbq-{uuid4().hex[:8]}",
    )


def _make_user(
    locale: str = "fa",
    bot_state: str | None = None,
    bot_state_data: dict[str, Any] | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.locale = locale
    user.bot_state = bot_state
    user.bot_state_data = bot_state_data
    user.messaging_account_ref = "ref-1"
    return user


def _make_cluster(
    cluster_id: Any = None,
    summary: str = "Test policy",
) -> MagicMock:
    cluster = MagicMock()
    cluster.id = cluster_id or uuid4()
    cluster.summary = summary
    cluster.options = []
    return cluster


def _make_option(cluster_id: Any, position: int = 1, label: str = "Option A") -> MagicMock:
    opt = MagicMock()
    opt.id = uuid4()
    opt.cluster_id = cluster_id
    opt.position = position
    opt.label = label
    opt.label_en = f"{label} EN"
    opt.description = f"Description for {label}"
    opt.description_en = f"EN description for {label}"
    return opt


# ---------------------------------------------------------------------------
# Linking flow (text messages from unknown users)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.handlers.commands.get_settings")
async def test_route_unknown_user_prompts_registration(mock_settings: MagicMock) -> None:
    mock_settings.return_value.app_public_base_url = "https://example.com"
    channel = FakeChannel()
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    with patch(
        "src.handlers.identity.resolve_linking_code",
        new_callable=AsyncMock,
        return_value=(False, "invalid", None),
    ):
        status = await route_message(session=db, message=_text_msg("hello", "unknown-ref"), channel=channel)

    assert status == "registration_prompted"
    expected = REGISTER_HINT.format(url="https://example.com")
    assert any(expected in m.text for m in channel.messages)


@pytest.mark.asyncio
async def test_route_successful_linking_sends_welcome_with_menu() -> None:
    channel = FakeChannel()
    db = AsyncMock()

    linked_user = _make_user(locale="en")
    no_user_result = MagicMock()
    no_user_result.scalar_one_or_none.return_value = None
    linked_user_result = MagicMock()
    linked_user_result.scalar_one_or_none.return_value = linked_user
    db.execute.side_effect = [no_user_result, linked_user_result]

    with patch(
        "src.handlers.identity.resolve_linking_code",
        new_callable=AsyncMock,
        return_value=(True, "linked", "t***t@example.com"),
    ):
        status = await route_message(session=db, message=_text_msg("_TC856VsVWs", "new-ref"), channel=channel)

    assert status == "account_linked"
    assert len(channel.messages) == 1
    text = channel.messages[0].text
    assert "t***t@example.com" in text
    assert "✅" in text
    assert "Welcome to Collective Will" in text
    markup = channel.messages[0].reply_markup
    assert markup is not None
    assert "inline_keyboard" in markup


@pytest.mark.asyncio
async def test_route_successful_linking_sends_welcome_fa() -> None:
    channel = FakeChannel()
    db = AsyncMock()

    linked_user = _make_user(locale="fa")
    no_user_result = MagicMock()
    no_user_result.scalar_one_or_none.return_value = None
    linked_user_result = MagicMock()
    linked_user_result.scalar_one_or_none.return_value = linked_user
    db.execute.side_effect = [no_user_result, linked_user_result]

    with patch(
        "src.handlers.identity.resolve_linking_code",
        new_callable=AsyncMock,
        return_value=(True, "linked", "t***t@example.com"),
    ):
        status = await route_message(session=db, message=_text_msg("_TC856VsVWs", "new-ref"), channel=channel)

    assert status == "account_linked"
    text = channel.messages[0].text
    assert "خوش آمدید" in text


# ---------------------------------------------------------------------------
# Callback: submit concern flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_submit_sets_awaiting_state() -> None:
    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_callback_msg("submit"), channel=channel)
    assert status == "awaiting_submission"
    assert user.bot_state == "awaiting_submission"
    assert len(channel.messages) == 1
    assert _MESSAGES["en"]["submission_prompt"] in channel.messages[0].text
    assert channel.answered_callbacks


@pytest.mark.asyncio
@patch("src.handlers.commands.handle_submission", new_callable=AsyncMock)
async def test_text_in_awaiting_state_triggers_submission(mock_intake: AsyncMock) -> None:
    user = _make_user(locale="en", bot_state="awaiting_submission")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(
        session=db, message=_text_msg("I am worried about economy"), channel=channel
    )
    assert status == "submission_received"
    mock_intake.assert_called_once()
    assert user.bot_state is None
    assert any(m.reply_markup and "inline_keyboard" in m.reply_markup for m in channel.messages)


# ---------------------------------------------------------------------------
# Callback: cancel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_cancel_clears_state_and_sends_menu() -> None:
    user = _make_user(locale="fa", bot_state="awaiting_submission")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_callback_msg("cancel"), channel=channel)
    assert status == "cancelled"
    assert user.bot_state is None
    assert user.bot_state_data is None
    assert any(m.reply_markup for m in channel.messages)


# ---------------------------------------------------------------------------
# Callback: language toggle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_lang_toggles_locale() -> None:
    user = _make_user(locale="fa")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_callback_msg("lang"), channel=channel)
    assert status == "language_updated"
    assert user.locale == "en"
    menu_msg = channel.messages[-1]
    assert menu_msg.reply_markup is not None


# ---------------------------------------------------------------------------
# Callback: vote (no active cycle)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_vote_no_active_cycle() -> None:
    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cycle_scalars = MagicMock()
    cycle_scalars.first.return_value = None
    cycle_result = MagicMock()
    cycle_result.scalars.return_value = cycle_scalars

    db.execute.side_effect = [user_result, cycle_result]

    status = await route_message(session=db, message=_callback_msg("vote"), channel=channel)
    assert status == "no_active_cycle"
    assert any(_MESSAGES["en"]["no_active_cycle"] in m.text for m in channel.messages)


# ---------------------------------------------------------------------------
# Callback: vote with active cycle shows first policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_vote_with_cycle_shows_first_policy() -> None:
    user = _make_user(locale="en")
    cluster1_id = uuid4()
    cluster2_id = uuid4()
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cycle = MagicMock()
    cycle.id = uuid4()
    cycle.cluster_ids = [cluster1_id, cluster2_id]
    cycle.status = "active"
    cycle_scalars = MagicMock()
    cycle_scalars.first.return_value = cycle
    cycle_result = MagicMock()
    cycle_result.scalars.return_value = cycle_scalars

    opt1 = _make_option(cluster1_id, 1, "Support")
    opt2 = _make_option(cluster1_id, 2, "Oppose")
    cluster1 = _make_cluster(cluster1_id, "Healthcare policy")
    cluster1.options = [opt1, opt2]

    cluster_scalars = MagicMock()
    cluster_scalars.scalar_one_or_none = MagicMock(return_value=cluster1)
    cluster_result = MagicMock()
    cluster_result.scalar_one_or_none = MagicMock(return_value=cluster1)

    db.execute.side_effect = [user_result, cycle_result, cluster_result]

    status = await route_message(session=db, message=_callback_msg("vote"), channel=channel)
    assert status == "policy_shown"
    assert user.bot_state == "voting"
    assert user.bot_state_data is not None
    assert user.bot_state_data["current_idx"] == 0
    assert len(user.bot_state_data["cluster_ids"]) == 2

    assert len(channel.messages) >= 1
    ballot_msg = channel.messages[0]
    assert "Policy 1 of 2" in ballot_msg.text
    assert ballot_msg.reply_markup is not None
    keyboard = ballot_msg.reply_markup["inline_keyboard"]
    option_labels = [row[0]["text"] for row in keyboard if row[0].get("callback_data", "").startswith("vo:")]
    assert len(option_labels) == 2


# ---------------------------------------------------------------------------
# Callback: option select advances to next policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_option_select_advances_to_next() -> None:
    cluster1_id = uuid4()
    cluster2_id = uuid4()
    session_data = {
        "cycle_id": str(uuid4()),
        "cluster_ids": [str(cluster1_id), str(cluster2_id)],
        "current_idx": 0,
        "selections": {},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    opt_a = _make_option(cluster1_id, 1, "Option A")
    opt_b = _make_option(cluster1_id, 2, "Option B")
    cluster1 = _make_cluster(cluster1_id)
    cluster1.options = [opt_a, opt_b]

    cluster2 = _make_cluster(cluster2_id, "Second policy")
    opt_c = _make_option(cluster2_id, 1, "Option C")
    cluster2.options = [opt_c]

    cluster1_result = MagicMock()
    cluster1_result.scalar_one_or_none.return_value = cluster1

    cluster2_result = MagicMock()
    cluster2_result.scalar_one_or_none.return_value = cluster2

    db.execute.side_effect = [user_result, cluster1_result, cluster2_result]

    status = await route_message(session=db, message=_callback_msg("vo:1"), channel=channel)
    assert status == "policy_shown"
    assert user.bot_state_data["current_idx"] == 1
    assert str(cluster1_id) in user.bot_state_data["selections"]
    assert user.bot_state_data["selections"][str(cluster1_id)] == str(opt_a.id)


# ---------------------------------------------------------------------------
# Callback: skip cluster
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skip_cluster_advances() -> None:
    cluster1_id = uuid4()
    cluster2_id = uuid4()
    session_data = {
        "cycle_id": str(uuid4()),
        "cluster_ids": [str(cluster1_id), str(cluster2_id)],
        "current_idx": 0,
        "selections": {},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster2 = _make_cluster(cluster2_id)
    opt = _make_option(cluster2_id, 1, "Opt")
    cluster2.options = [opt]
    cluster2_result = MagicMock()
    cluster2_result.scalar_one_or_none.return_value = cluster2

    db.execute.side_effect = [user_result, cluster2_result]

    status = await route_message(session=db, message=_callback_msg("vsk"), channel=channel)
    assert status == "policy_shown"
    assert user.bot_state_data["current_idx"] == 1
    assert str(cluster1_id) not in user.bot_state_data["selections"]


# ---------------------------------------------------------------------------
# Callback: vote back
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vote_back_goes_to_previous() -> None:
    cluster1_id = uuid4()
    cluster2_id = uuid4()
    session_data = {
        "cycle_id": str(uuid4()),
        "cluster_ids": [str(cluster1_id), str(cluster2_id)],
        "current_idx": 1,
        "selections": {},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster1 = _make_cluster(cluster1_id)
    opt = _make_option(cluster1_id, 1, "Opt")
    cluster1.options = [opt]
    cluster1_result = MagicMock()
    cluster1_result.scalar_one_or_none.return_value = cluster1

    db.execute.side_effect = [user_result, cluster1_result]

    status = await route_message(session=db, message=_callback_msg("vbk"), channel=channel)
    assert status == "policy_shown"
    assert user.bot_state_data["current_idx"] == 0


# ---------------------------------------------------------------------------
# Callback: vote submit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.handlers.commands.cast_vote", new_callable=AsyncMock)
@patch("src.handlers.commands.get_settings")
async def test_vote_submit_calls_cast_vote(mock_settings: MagicMock, mock_cast: AsyncMock) -> None:
    mock_settings.return_value.min_account_age_hours = 48
    mock_settings.return_value.require_contribution_for_vote = True
    mock_settings.return_value.app_public_base_url = "https://example.com"

    cluster1_id = uuid4()
    opt_id = uuid4()
    cycle_id = uuid4()
    session_data = {
        "cycle_id": str(cycle_id),
        "cluster_ids": [str(cluster1_id)],
        "current_idx": 1,
        "selections": {str(cluster1_id): str(opt_id)},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cycle = MagicMock()
    cycle.id = cycle_id
    cycle.status = "active"
    cycle_result = MagicMock()
    cycle_result.scalar_one_or_none.return_value = cycle

    db.execute.side_effect = [user_result, cycle_result]

    vote_mock = MagicMock()
    vote_mock.id = uuid4()
    mock_cast.return_value = (vote_mock, "recorded")

    status = await route_message(session=db, message=_callback_msg("vsub"), channel=channel)
    assert status == "vote_recorded"
    mock_cast.assert_called_once()
    call_kwargs = mock_cast.call_args.kwargs
    assert call_kwargs["selections"] == [{"cluster_id": str(cluster1_id), "option_id": str(opt_id)}]
    assert user.bot_state is None
    assert user.bot_state_data is None
    assert any(_MESSAGES["en"]["vote_recorded"] in m.text for m in channel.messages)


# ---------------------------------------------------------------------------
# Callback: vote submit — empty selections
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vote_submit_empty_selections_returns_to_menu() -> None:
    cycle_id = uuid4()
    session_data = {
        "cycle_id": str(cycle_id),
        "cluster_ids": [str(uuid4())],
        "current_idx": 1,
        "selections": {},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cycle = MagicMock()
    cycle.id = cycle_id
    cycle.status = "active"
    cycle_result = MagicMock()
    cycle_result.scalar_one_or_none.return_value = cycle

    db.execute.side_effect = [user_result, cycle_result]

    status = await route_message(session=db, message=_callback_msg("vsub"), channel=channel)
    assert status == "empty_vote"
    assert user.bot_state is None
    assert user.bot_state_data is None


# ---------------------------------------------------------------------------
# Callback: vote submit — cycle expired
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vote_submit_cycle_expired() -> None:
    cycle_id = uuid4()
    session_data = {
        "cycle_id": str(cycle_id),
        "cluster_ids": [str(uuid4())],
        "current_idx": 1,
        "selections": {str(uuid4()): str(uuid4())},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cycle = MagicMock()
    cycle.id = cycle_id
    cycle.status = "tallied"
    cycle_result = MagicMock()
    cycle_result.scalar_one_or_none.return_value = cycle

    db.execute.side_effect = [user_result, cycle_result]

    status = await route_message(session=db, message=_callback_msg("vsub"), channel=channel)
    assert status == "no_active_cycle"
    assert user.bot_state is None


# ---------------------------------------------------------------------------
# Callback: vote submit — cast_vote rejects
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.handlers.commands.cast_vote", new_callable=AsyncMock)
@patch("src.handlers.commands.get_settings")
async def test_vote_submit_rejected(mock_settings: MagicMock, mock_cast: AsyncMock) -> None:
    mock_settings.return_value.min_account_age_hours = 48
    mock_settings.return_value.require_contribution_for_vote = True
    mock_settings.return_value.app_public_base_url = "https://example.com"
    mock_cast.return_value = (None, "not_eligible")

    cycle_id = uuid4()
    cid = str(uuid4())
    session_data = {
        "cycle_id": str(cycle_id),
        "cluster_ids": [cid],
        "current_idx": 1,
        "selections": {cid: str(uuid4())},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cycle = MagicMock()
    cycle.id = cycle_id
    cycle.status = "active"
    cycle_result = MagicMock()
    cycle_result.scalar_one_or_none.return_value = cycle

    db.execute.side_effect = [user_result, cycle_result]

    status = await route_message(session=db, message=_callback_msg("vsub"), channel=channel)
    assert status == "not_eligible"
    assert any("Vote rejected" in m.text for m in channel.messages)


# ---------------------------------------------------------------------------
# Callback: option select without active vote session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_option_select_no_session_returns_menu() -> None:
    user = _make_user(locale="en", bot_state=None, bot_state_data=None)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_callback_msg("vo:1"), channel=channel)
    assert status == "no_vote_session"
    assert any(m.reply_markup for m in channel.messages)


# ---------------------------------------------------------------------------
# Callback: vote change (restart from summary)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vote_change_resets_to_first_policy() -> None:
    cluster1_id = uuid4()
    cluster2_id = uuid4()
    session_data = {
        "cycle_id": str(uuid4()),
        "cluster_ids": [str(cluster1_id), str(cluster2_id)],
        "current_idx": 2,
        "selections": {str(cluster1_id): str(uuid4())},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster1 = _make_cluster(cluster1_id)
    opt = _make_option(cluster1_id, 1, "Opt")
    cluster1.options = [opt]
    cluster1_result = MagicMock()
    cluster1_result.scalar_one_or_none.return_value = cluster1

    db.execute.side_effect = [user_result, cluster1_result]

    status = await route_message(session=db, message=_callback_msg("vchg"), channel=channel)
    assert status == "policy_shown"
    assert user.bot_state_data["current_idx"] == 0


# ---------------------------------------------------------------------------
# Endorsement flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.handlers.commands.count_cluster_endorsements", new_callable=AsyncMock)
@patch("src.handlers.commands.get_user_endorsed_cluster_ids", new_callable=AsyncMock)
async def test_endorse_menu_no_clusters(
    mock_endorsed: AsyncMock, mock_count: AsyncMock
) -> None:
    """Endorse callback with no endorsable clusters shows message + menu."""
    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    empty_clusters = MagicMock()
    empty_clusters.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

    empty_cycles = MagicMock()
    empty_cycles.all.return_value = []

    db.execute.side_effect = [user_result, empty_clusters, empty_cycles]

    status = await route_message(session=db, message=_callback_msg("endorse"), channel=channel)
    assert status == "no_endorsable_clusters"
    assert any(_MESSAGES["en"]["no_endorsable_clusters"] in m.text for m in channel.messages)


@pytest.mark.asyncio
@patch("src.handlers.commands.count_cluster_endorsements", new_callable=AsyncMock)
@patch("src.handlers.commands.get_user_endorsed_cluster_ids", new_callable=AsyncMock)
async def test_endorse_menu_shows_first_cluster(
    mock_endorsed: AsyncMock, mock_count: AsyncMock
) -> None:
    """Endorse callback with endorsable clusters shows first cluster."""
    mock_endorsed.return_value = set()
    mock_count.return_value = 3

    cluster_id = uuid4()
    cluster = MagicMock()
    cluster.id = cluster_id
    cluster.ballot_question = "Should we address internet censorship?"
    cluster.ballot_question_fa = "آیا باید سانسور اینترنت را بررسی کنیم؟"
    cluster.summary = "Internet censorship policy"
    cluster.member_count = 8
    cluster.created_at = None

    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster_list = MagicMock()
    cluster_list.scalars.return_value = MagicMock(all=MagicMock(return_value=[cluster]))

    empty_cycles = MagicMock()
    empty_cycles.all.return_value = []

    cluster_result = MagicMock()
    cluster_result.scalar_one_or_none.return_value = cluster

    db.execute.side_effect = [user_result, cluster_list, empty_cycles, cluster_result]

    status = await route_message(session=db, message=_callback_msg("endorse"), channel=channel)
    assert status == "endorse_policy_shown"
    assert user.bot_state == "endorsing"
    last_msg = channel.messages[-1]
    assert "internet censorship" in last_msg.text.lower()
    assert last_msg.reply_markup is not None
    cb_data = [
        btn["callback_data"]
        for row in last_msg.reply_markup["inline_keyboard"]
        for btn in row
    ]
    assert "e:1" in cb_data
    assert "esk" in cb_data


@pytest.mark.asyncio
@patch("src.handlers.commands.count_cluster_endorsements", new_callable=AsyncMock)
@patch("src.handlers.commands.record_endorsement", new_callable=AsyncMock)
async def test_endorse_callback_from_session(
    mock_endorse: AsyncMock, mock_count: AsyncMock
) -> None:
    """e:{N} from endorsement session records endorsement and advances."""
    mock_endorse.return_value = (True, "recorded")
    mock_count.return_value = 5

    cluster1_id = uuid4()
    cluster2_id = uuid4()
    session_data = {
        "endorsing": True,
        "cluster_ids": [str(cluster1_id), str(cluster2_id)],
        "current_idx": 0,
    }
    user = _make_user(locale="en", bot_state="endorsing", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster2 = MagicMock()
    cluster2.id = cluster2_id
    cluster2.ballot_question = "Education reform?"
    cluster2.ballot_question_fa = None
    cluster2.summary = "Education policy"
    cluster2.member_count = 4

    cluster2_result = MagicMock()
    cluster2_result.scalar_one_or_none.return_value = cluster2

    db.execute.side_effect = [user_result, cluster2_result]

    status = await route_message(session=db, message=_callback_msg("e:1"), channel=channel)
    assert status == "endorse_policy_shown"
    mock_endorse.assert_called_once()
    assert any(_MESSAGES["en"]["endorsement_recorded"] in m.text for m in channel.messages)
    assert session_data["current_idx"] == 1


@pytest.mark.asyncio
@patch("src.handlers.commands.count_cluster_endorsements", new_callable=AsyncMock)
async def test_endorse_skip(mock_count: AsyncMock) -> None:
    """esk advances to the next cluster without endorsing."""
    mock_count.return_value = 2

    cluster1_id = uuid4()
    cluster2_id = uuid4()
    session_data = {
        "endorsing": True,
        "cluster_ids": [str(cluster1_id), str(cluster2_id)],
        "current_idx": 0,
    }
    user = _make_user(locale="en", bot_state="endorsing", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster2 = MagicMock()
    cluster2.id = cluster2_id
    cluster2.ballot_question = "Healthcare?"
    cluster2.ballot_question_fa = None
    cluster2.summary = "Healthcare policy"
    cluster2.member_count = 6

    cluster2_result = MagicMock()
    cluster2_result.scalar_one_or_none.return_value = cluster2

    db.execute.side_effect = [user_result, cluster2_result]

    status = await route_message(session=db, message=_callback_msg("esk"), channel=channel)
    assert status == "endorse_policy_shown"
    assert session_data["current_idx"] == 1


@pytest.mark.asyncio
@patch("src.handlers.commands.count_cluster_endorsements", new_callable=AsyncMock)
async def test_endorse_back(mock_count: AsyncMock) -> None:
    """ebk goes back to the previous cluster."""
    mock_count.return_value = 2

    cluster1_id = uuid4()
    cluster2_id = uuid4()
    session_data = {
        "endorsing": True,
        "cluster_ids": [str(cluster1_id), str(cluster2_id)],
        "current_idx": 1,
    }
    user = _make_user(locale="en", bot_state="endorsing", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster1 = MagicMock()
    cluster1.id = cluster1_id
    cluster1.ballot_question = "Internet policy?"
    cluster1.ballot_question_fa = None
    cluster1.summary = "Internet policy"
    cluster1.member_count = 5

    cluster1_result = MagicMock()
    cluster1_result.scalar_one_or_none.return_value = cluster1

    db.execute.side_effect = [user_result, cluster1_result]

    status = await route_message(session=db, message=_callback_msg("ebk"), channel=channel)
    assert status == "endorse_policy_shown"
    assert session_data["current_idx"] == 0


@pytest.mark.asyncio
async def test_endorse_without_session_returns_menu() -> None:
    """e:{N} without an active endorsement session returns to menu."""
    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_callback_msg("e:1"), channel=channel)
    assert status == "no_endorse_session"


@pytest.mark.asyncio
async def test_endorse_last_cluster_returns_to_menu() -> None:
    """After last cluster, endorsement flow clears state and returns to menu."""
    cluster1_id = uuid4()
    session_data = {
        "endorsing": True,
        "cluster_ids": [str(cluster1_id)],
        "current_idx": 1,
    }
    user = _make_user(locale="en", bot_state="endorsing", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_callback_msg("esk"), channel=channel)
    assert status == "endorse_done"
    assert user.bot_state is None
    assert user.bot_state_data is None


@pytest.mark.asyncio
@patch("src.handlers.commands.count_cluster_endorsements", new_callable=AsyncMock)
@patch("src.handlers.commands.get_user_endorsed_cluster_ids", new_callable=AsyncMock)
async def test_endorse_menu_all_already_endorsed(
    mock_endorsed: AsyncMock, mock_count: AsyncMock
) -> None:
    """When all clusters are already endorsed, show no-endorsable message."""
    cluster_id = uuid4()
    mock_endorsed.return_value = {cluster_id}
    mock_count.return_value = 5

    cluster = MagicMock()
    cluster.id = cluster_id
    cluster.ballot_question = "Some policy?"
    cluster.created_at = None

    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster_list = MagicMock()
    cluster_list.scalars.return_value = MagicMock(all=MagicMock(return_value=[cluster]))

    empty_cycles = MagicMock()
    empty_cycles.all.return_value = []

    db.execute.side_effect = [user_result, cluster_list, empty_cycles]

    status = await route_message(session=db, message=_callback_msg("endorse"), channel=channel)
    assert status == "no_endorsable_clusters"
    assert any(_MESSAGES["en"]["no_endorsable_clusters"] in m.text for m in channel.messages)


@pytest.mark.asyncio
@patch("src.handlers.commands.count_cluster_endorsements", new_callable=AsyncMock)
@patch("src.handlers.commands.get_user_endorsed_cluster_ids", new_callable=AsyncMock)
async def test_endorse_menu_excludes_active_cycle_clusters(
    mock_endorsed: AsyncMock, mock_count: AsyncMock
) -> None:
    """Clusters in active voting cycles are excluded from endorsement."""
    mock_endorsed.return_value = set()
    mock_count.return_value = 0

    active_cluster_id = uuid4()
    endorsable_cluster_id = uuid4()

    active_cluster = MagicMock()
    active_cluster.id = active_cluster_id
    active_cluster.ballot_question = "Active cycle policy"
    active_cluster.created_at = None

    endorsable_cluster = MagicMock()
    endorsable_cluster.id = endorsable_cluster_id
    endorsable_cluster.ballot_question = "Pre-ballot policy"
    endorsable_cluster.ballot_question_fa = None
    endorsable_cluster.summary = "Pre-ballot"
    endorsable_cluster.member_count = 3
    endorsable_cluster.created_at = None

    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cluster_list = MagicMock()
    cluster_list.scalars.return_value = MagicMock(
        all=MagicMock(return_value=[active_cluster, endorsable_cluster])
    )

    cycles_result = MagicMock()
    cycles_result.all.return_value = [([active_cluster_id],)]

    cluster_result = MagicMock()
    cluster_result.scalar_one_or_none.return_value = endorsable_cluster

    db.execute.side_effect = [user_result, cluster_list, cycles_result, cluster_result]

    status = await route_message(session=db, message=_callback_msg("endorse"), channel=channel)
    assert status == "endorse_policy_shown"
    assert user.bot_state_data["cluster_ids"] == [str(endorsable_cluster_id)]


# ---------------------------------------------------------------------------
# Vote summary shown after last policy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_last_policy_option_select_shows_summary() -> None:
    cluster1_id = uuid4()
    session_data = {
        "cycle_id": str(uuid4()),
        "cluster_ids": [str(cluster1_id)],
        "current_idx": 0,
        "selections": {},
    }
    user = _make_user(locale="en", bot_state="voting", bot_state_data=session_data)
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    opt_a = _make_option(cluster1_id, 1, "Option A")
    cluster1 = _make_cluster(cluster1_id, "Healthcare")
    cluster1.options = [opt_a]

    cluster1_result = MagicMock()
    cluster1_result.scalar_one_or_none.return_value = cluster1

    # After selection: _show_current_policy sees idx=1 >= total=1,
    # so it calls _show_vote_summary which queries DB twice per cluster.
    summary_cluster_result = MagicMock()
    summary_cluster_result.scalar_one_or_none.return_value = cluster1

    db.execute.side_effect = [
        user_result,
        cluster1_result,       # _load_cluster_with_options for option select
        cluster1_result,       # _load_cluster_with_options in summary (cache)
        summary_cluster_result,  # select(Cluster) in summary loop
    ]

    status = await route_message(session=db, message=_callback_msg("vo:1"), channel=channel)
    assert status == "summary_shown"
    assert user.bot_state_data["current_idx"] == 1
    summary_msg = channel.messages[-1]
    assert "Your selections" in summary_msg.text
    assert summary_msg.reply_markup is not None
    keyboard_data = [
        btn["callback_data"]
        for row in summary_msg.reply_markup["inline_keyboard"]
        for btn in row
    ]
    assert "vsub" in keyboard_data
    assert "vchg" in keyboard_data


# ---------------------------------------------------------------------------
# Unrecognized text re-sends menu
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unrecognized_text_resends_menu() -> None:
    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_text_msg("random text"), channel=channel)
    assert status == "menu_resent"
    assert len(channel.messages) == 1
    assert _MESSAGES["en"]["menu_hint"] in channel.messages[0].text
    assert channel.messages[0].reply_markup is not None


# ---------------------------------------------------------------------------
# Static message content tests
# ---------------------------------------------------------------------------

def test_register_hint_is_bilingual() -> None:
    rendered = REGISTER_HINT.format(url="https://example.com")
    assert "please sign up" in rendered
    assert "https://example.com" in rendered
    assert "ثبت‌نام" in rendered


def test_welcome_messages_have_both_locales() -> None:
    en_text = _WELCOME["en"].format(email="t***t@test.com")
    assert "Welcome to Collective Will" in en_text
    assert "t***t@test.com" in en_text

    fa_text = _WELCOME["fa"].format(email="t***t@test.com")
    assert "خوش آمدید" in fa_text
    assert "t***t@test.com" in fa_text
