from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.channels.telegram import TelegramChannel
from src.channels.types import OutboundMessage

VALID_PAYLOAD = {
    "update_id": 123456789,
    "message": {
        "message_id": 42,
        "from": {"id": 987654321, "is_bot": False, "first_name": "Test"},
        "chat": {"id": 987654321, "type": "private"},
        "date": 1707000000,
        "text": "وضعیت اقتصادی خیلی بد است",
    },
}

CALLBACK_PAYLOAD = {
    "update_id": 123456790,
    "callback_query": {
        "id": "cbq-12345",
        "from": {"id": 987654321, "is_bot": False, "first_name": "Test"},
        "message": {
            "message_id": 99,
            "chat": {"id": 987654321, "type": "private"},
            "date": 1707000000,
            "text": "Previous message",
        },
        "data": "submit",
    },
}


def _make_channel() -> TelegramChannel:
    return TelegramChannel(bot_token="fake-token", session=AsyncMock())


# ---------------------------------------------------------------------------
# Text message parsing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.channels.telegram.get_or_create_account_ref", new_callable=AsyncMock, return_value="opaque-ref-abc")
async def test_parse_webhook_extracts_text_and_sender_ref(mock_mapping: AsyncMock) -> None:
    channel = _make_channel()
    msg = await channel.parse_webhook(VALID_PAYLOAD)
    assert msg is not None
    assert msg.text == "وضعیت اقتصادی خیلی بد است"
    assert msg.sender_ref == "opaque-ref-abc"
    assert msg.platform == "telegram"
    assert msg.message_id == "42"
    assert msg.raw_payload == VALID_PAYLOAD
    assert msg.callback_data is None
    assert msg.callback_query_id is None
    mock_mapping.assert_called_once_with(channel._session, "telegram", "987654321")


@pytest.mark.asyncio
async def test_parse_webhook_returns_none_for_photo_message() -> None:
    channel = _make_channel()
    payload = {
        "update_id": 2,
        "message": {
            "message_id": 43,
            "from": {"id": 987654321, "is_bot": False},
            "chat": {"id": 987654321, "type": "private"},
            "date": 1707000000,
            "photo": [{"file_id": "ABC", "width": 100, "height": 100}],
        },
    }
    assert await channel.parse_webhook(payload) is None


@pytest.mark.asyncio
async def test_parse_webhook_returns_none_for_edited_message() -> None:
    channel = _make_channel()
    payload = {
        "update_id": 3,
        "edited_message": {
            "message_id": 44,
            "chat": {"id": 987654321, "type": "private"},
            "date": 1707000000,
            "text": "edited text",
        },
    }
    assert await channel.parse_webhook(payload) is None


@pytest.mark.asyncio
async def test_parse_webhook_returns_none_when_message_key_absent() -> None:
    channel = _make_channel()
    payload = {"update_id": 4, "channel_post": {"text": "channel post"}}
    assert await channel.parse_webhook(payload) is None


@pytest.mark.asyncio
@patch("src.channels.telegram.get_or_create_account_ref", new_callable=AsyncMock)
async def test_resolve_idempotent(mock_mapping: AsyncMock) -> None:
    ref = str(uuid4())
    mock_mapping.return_value = ref
    channel = _make_channel()
    msg1 = await channel.parse_webhook(VALID_PAYLOAD)
    msg2 = await channel.parse_webhook(VALID_PAYLOAD)
    assert msg1 is not None and msg2 is not None
    assert msg1.sender_ref == msg2.sender_ref


# ---------------------------------------------------------------------------
# Callback query parsing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.channels.telegram.get_or_create_account_ref", new_callable=AsyncMock, return_value="opaque-ref-abc")
async def test_parse_callback_query(mock_mapping: AsyncMock) -> None:
    channel = _make_channel()
    msg = await channel.parse_webhook(CALLBACK_PAYLOAD)
    assert msg is not None
    assert msg.callback_data == "submit"
    assert msg.callback_query_id == "cbq-12345"
    assert msg.sender_ref == "opaque-ref-abc"
    assert msg.text == ""
    assert msg.message_id == "99"
    assert msg.platform == "telegram"
    mock_mapping.assert_called_once_with(channel._session, "telegram", "987654321")


@pytest.mark.asyncio
@patch("src.channels.telegram.get_or_create_account_ref", new_callable=AsyncMock, return_value="opaque-ref")
async def test_parse_callback_query_with_vote_data(mock_mapping: AsyncMock) -> None:
    channel = _make_channel()
    payload = {
        "update_id": 999,
        "callback_query": {
            "id": "cbq-vote",
            "from": {"id": 111, "is_bot": False},
            "message": {
                "message_id": 200,
                "chat": {"id": 111, "type": "private"},
                "date": 1707000000,
            },
            "data": "vt:010:1",
        },
    }
    msg = await channel.parse_webhook(payload)
    assert msg is not None
    assert msg.callback_data == "vt:010:1"
    assert msg.callback_query_id == "cbq-vote"


# ---------------------------------------------------------------------------
# send_message with reply_markup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.channels.telegram.get_platform_id_by_ref", new_callable=AsyncMock, return_value="12345")
async def test_send_message_calls_correct_endpoint(
    mock_reverse: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = _make_channel()
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    async def _fake_post(self: object, url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("src.channels.telegram.httpx.AsyncClient.post", _fake_post)
    result = await channel.send_message(OutboundMessage(recipient_ref="opaque-ref", text="hi", platform="telegram"))
    assert result is True
    assert "fake-token/sendMessage" in str(captured["url"])
    json_body = captured["kwargs"].get("json", {})
    assert isinstance(json_body, dict)
    assert json_body["chat_id"] == "12345"
    assert json_body["text"] == "hi"
    assert "reply_markup" not in json_body


@pytest.mark.asyncio
@patch("src.channels.telegram.get_platform_id_by_ref", new_callable=AsyncMock, return_value="12345")
async def test_send_message_passes_reply_markup(
    mock_reverse: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = _make_channel()
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    async def _fake_post(self: object, url: str, **kwargs: object) -> FakeResponse:
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("src.channels.telegram.httpx.AsyncClient.post", _fake_post)
    markup = {"inline_keyboard": [[{"text": "Test", "callback_data": "test"}]]}
    result = await channel.send_message(
        OutboundMessage(recipient_ref="opaque-ref", text="hi", platform="telegram", reply_markup=markup)
    )
    assert result is True
    json_body = captured["kwargs"].get("json", {})
    assert json_body["reply_markup"] == markup


@pytest.mark.asyncio
@patch("src.channels.telegram.get_platform_id_by_ref", new_callable=AsyncMock, return_value="12345")
async def test_send_message_returns_false_on_http_error(
    mock_reverse: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    channel = _make_channel()

    class FakeResponse:
        status_code = 403

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("forbidden", request=httpx.Request("POST", "http://x"), response=self)  # type: ignore[arg-type]

    async def _fake_post(self: object, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("src.channels.telegram.httpx.AsyncClient.post", _fake_post)
    result = await channel.send_message(OutboundMessage(recipient_ref="opaque-ref", text="hi", platform="telegram"))
    assert result is False


@pytest.mark.asyncio
@patch("src.channels.telegram.get_platform_id_by_ref", new_callable=AsyncMock, return_value=None)
async def test_send_message_returns_false_for_unknown_ref(mock_reverse: AsyncMock) -> None:
    channel = _make_channel()
    result = await channel.send_message(OutboundMessage(recipient_ref="unknown-ref", text="hi", platform="telegram"))
    assert result is False


# ---------------------------------------------------------------------------
# answer_callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_callback_calls_api(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = _make_channel()
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    async def _fake_post(self: object, url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("src.channels.telegram.httpx.AsyncClient.post", _fake_post)
    result = await channel.answer_callback("cbq-123")
    assert result is True
    assert "answerCallbackQuery" in str(captured["url"])
    json_body = captured["kwargs"].get("json", {})
    assert json_body["callback_query_id"] == "cbq-123"


# ---------------------------------------------------------------------------
# edit_message_markup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.channels.telegram.get_platform_id_by_ref", new_callable=AsyncMock, return_value="12345")
async def test_edit_message_markup_calls_api(
    mock_reverse: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = _make_channel()
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    async def _fake_post(self: object, url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("src.channels.telegram.httpx.AsyncClient.post", _fake_post)
    markup = {"inline_keyboard": [[{"text": "✅ 1", "callback_data": "vt:1:1"}]]}
    result = await channel.edit_message_markup("opaque-ref", "99", markup)
    assert result is True
    assert "editMessageReplyMarkup" in str(captured["url"])
    json_body = captured["kwargs"].get("json", {})
    assert json_body["chat_id"] == "12345"
    assert json_body["message_id"] == 99
    assert json_body["reply_markup"] == markup


# ---------------------------------------------------------------------------
# Privacy: raw chat_id not in unified message
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.channels.telegram.get_or_create_account_ref", new_callable=AsyncMock, return_value="opaque-ref")
async def test_raw_chat_id_not_in_unified_message(mock_mapping: AsyncMock) -> None:
    channel = _make_channel()
    msg = await channel.parse_webhook(VALID_PAYLOAD)
    assert msg is not None
    assert "987654321" not in msg.sender_ref
    assert "987654321" not in msg.message_id
