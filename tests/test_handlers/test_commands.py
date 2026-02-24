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
    HELP_FA,
    NO_ACTIVE_CYCLE_FA,
    REGISTER_HINT,
    SKIP_FA,
    detect_command,
    is_command,
    route_message,
)


class FakeChannel(BaseChannel):
    def __init__(self) -> None:
        self.messages: list[OutboundMessage] = []

    async def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        return None

    async def send_message(self, message: OutboundMessage) -> bool:
        self.messages.append(message)
        return True

    async def send_ballot(self, recipient_ref: str, policies: list[dict[str, Any]]) -> bool:
        return True


def _msg(text: str, sender_ref: str = "ref-1") -> UnifiedMessage:
    return UnifiedMessage(sender_ref=sender_ref, text=text, message_id=f"test-{uuid4().hex[:8]}")


def _make_user(locale: str = "fa") -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.locale = locale
    return user


# --- detect_command tests ---

def test_detect_command_status_farsi() -> None:
    assert detect_command("وضعیت") == "status"


def test_detect_command_status_english() -> None:
    assert detect_command("status") == "status"


def test_detect_command_status_case_insensitive() -> None:
    assert detect_command("STATUS") == "status"


def test_detect_command_help() -> None:
    assert detect_command("کمک") == "help"


def test_detect_command_sign() -> None:
    assert detect_command("امضا 3") == "sign"


def test_detect_command_ballot_numbers_not_command() -> None:
    assert detect_command("1, 3, 5") is None


def test_detect_command_freeform_not_command() -> None:
    assert detect_command("I am worried about inflation") is None


def test_detect_command_vote() -> None:
    assert detect_command("رای") == "vote"
    assert detect_command("vote") == "vote"


def test_detect_command_skip() -> None:
    assert detect_command("انصراف") == "skip"
    assert detect_command("skip") == "skip"


def test_detect_command_language() -> None:
    assert detect_command("زبان") == "language"
    assert detect_command("language") == "language"


def test_is_command_delegates() -> None:
    assert is_command("status") is True
    assert is_command("random text") is False


# --- route_message tests ---

@pytest.mark.asyncio
async def test_route_unknown_user_prompts_registration() -> None:
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
        status = await route_message(session=db, message=_msg("hello", "unknown-ref"), channel=channel)

    assert status == "registration_prompted"
    assert any(REGISTER_HINT in m.text for m in channel.messages)


@pytest.mark.asyncio
async def test_route_successful_linking_sends_welcome_en() -> None:
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
        status = await route_message(session=db, message=_msg("_TC856VsVWs", "new-ref"), channel=channel)

    assert status == "account_linked"
    assert len(channel.messages) == 1
    text = channel.messages[0].text
    assert "t***t@example.com" in text
    assert "✅" in text
    assert "Welcome to Collective Will" in text
    assert "Commands:" in text


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
        status = await route_message(session=db, message=_msg("_TC856VsVWs", "new-ref"), channel=channel)

    assert status == "account_linked"
    assert len(channel.messages) == 1
    text = channel.messages[0].text
    assert "t***t@example.com" in text
    assert "خوش آمدید" in text
    assert "دستورات:" in text


@pytest.mark.asyncio
async def test_route_status_command() -> None:
    user = _make_user(locale="fa")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    count_result = MagicMock()
    count_result.scalar_one.return_value = 3

    cycle_scalars = MagicMock()
    cycle_scalars.first.return_value = None
    cycle_result = MagicMock()
    cycle_result.scalars.return_value = cycle_scalars

    db.execute.side_effect = [user_result, count_result, count_result, cycle_result]

    status = await route_message(session=db, message=_msg("وضعیت"), channel=channel)
    assert status == "status_sent"
    assert channel.messages
    assert "📊" in channel.messages[0].text


@pytest.mark.asyncio
async def test_route_help_command_farsi() -> None:
    user = _make_user(locale="fa")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_msg("کمک"), channel=channel)
    assert status == "help_sent"
    assert any(HELP_FA in m.text for m in channel.messages)


@pytest.mark.asyncio
async def test_route_help_command_english() -> None:
    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_msg("help"), channel=channel)
    assert status == "help_sent"
    assert len(channel.messages) == 1
    assert _MESSAGES["en"]["help"] in channel.messages[0].text
    assert "Commands:" in channel.messages[0].text


@pytest.mark.asyncio
async def test_route_skip_command_farsi() -> None:
    user = _make_user(locale="fa")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_msg("انصراف"), channel=channel)
    assert status == "skipped"
    assert any(SKIP_FA in m.text for m in channel.messages)


@pytest.mark.asyncio
async def test_route_skip_command_english() -> None:
    user = _make_user(locale="en")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_msg("skip"), channel=channel)
    assert status == "skipped"
    assert _MESSAGES["en"]["skip"] in channel.messages[0].text


@pytest.mark.asyncio
async def test_route_language_toggle() -> None:
    user = _make_user(locale="fa")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    db.execute.return_value = user_result

    status = await route_message(session=db, message=_msg("زبان"), channel=channel)
    assert status == "language_updated"
    assert user.locale == "en"


@pytest.mark.asyncio
async def test_route_vote_no_active_cycle_farsi() -> None:
    user = _make_user(locale="fa")
    channel = FakeChannel()
    db = AsyncMock()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user

    cycle_scalars = MagicMock()
    cycle_scalars.first.return_value = None
    cycle_result = MagicMock()
    cycle_result.scalars.return_value = cycle_scalars

    db.execute.side_effect = [user_result, cycle_result]

    status = await route_message(session=db, message=_msg("رای"), channel=channel)
    assert status == "no_active_cycle"
    assert any(NO_ACTIVE_CYCLE_FA in m.text for m in channel.messages)


@pytest.mark.asyncio
async def test_route_vote_no_active_cycle_english() -> None:
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

    status = await route_message(session=db, message=_msg("vote"), channel=channel)
    assert status == "no_active_cycle"
    assert _MESSAGES["en"]["no_active_cycle"] in channel.messages[0].text


@pytest.mark.asyncio
@patch("src.handlers.commands.handle_submission", new_callable=AsyncMock)
async def test_route_freeform_to_intake(mock_intake: AsyncMock) -> None:
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

    status = await route_message(session=db, message=_msg("I am worried about economy"), channel=channel)
    assert status == "submission_received"
    mock_intake.assert_called_once()


@pytest.mark.asyncio
async def test_register_hint_is_bilingual() -> None:
    assert "Please sign up" in REGISTER_HINT
    assert "ثبت‌نام" in REGISTER_HINT


@pytest.mark.asyncio
async def test_welcome_messages_have_both_locales() -> None:
    en_text = _WELCOME["en"].format(email="t***t@test.com")
    assert "Welcome to Collective Will" in en_text
    assert "Commands:" in en_text
    assert "t***t@test.com" in en_text

    fa_text = _WELCOME["fa"].format(email="t***t@test.com")
    assert "خوش آمدید" in fa_text
    assert "دستورات:" in fa_text
    assert "t***t@test.com" in fa_text
