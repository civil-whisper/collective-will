from __future__ import annotations

import pytest

from src.channels.telegram import (
    _REVERSE_TG_MAPPING,
    _SEALED_TG_MAPPING,
    TelegramChannel,
    resolve_or_create_account_ref,
)
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


@pytest.fixture(autouse=True)
def _clear_mapping() -> None:
    _SEALED_TG_MAPPING.clear()
    _REVERSE_TG_MAPPING.clear()


def test_parse_webhook_extracts_text_and_sender_ref() -> None:
    channel = TelegramChannel(bot_token="fake-token")
    msg = channel.parse_webhook(VALID_PAYLOAD)
    assert msg is not None
    assert msg.text == "وضعیت اقتصادی خیلی بد است"
    assert msg.sender_ref != "987654321"
    assert msg.platform == "telegram"
    assert msg.message_id == "42"
    assert msg.raw_payload == VALID_PAYLOAD


def test_parse_webhook_returns_none_for_photo_message() -> None:
    channel = TelegramChannel(bot_token="fake-token")
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
    assert channel.parse_webhook(payload) is None


def test_parse_webhook_returns_none_for_edited_message() -> None:
    channel = TelegramChannel(bot_token="fake-token")
    payload = {
        "update_id": 3,
        "edited_message": {
            "message_id": 44,
            "chat": {"id": 987654321, "type": "private"},
            "date": 1707000000,
            "text": "edited text",
        },
    }
    assert channel.parse_webhook(payload) is None


def test_parse_webhook_returns_none_when_message_key_absent() -> None:
    channel = TelegramChannel(bot_token="fake-token")
    payload = {"update_id": 4, "channel_post": {"text": "channel post"}}
    assert channel.parse_webhook(payload) is None


def test_resolve_or_create_returns_existing_ref() -> None:
    ref1 = resolve_or_create_account_ref("tg-123")
    ref2 = resolve_or_create_account_ref("tg-123")
    assert ref1 == ref2


def test_resolve_or_create_new_uuid_for_unseen() -> None:
    ref = resolve_or_create_account_ref("tg-new")
    assert len(ref) == 36


def test_different_chat_ids_produce_different_refs() -> None:
    ref_a = resolve_or_create_account_ref("111")
    ref_b = resolve_or_create_account_ref("222")
    assert ref_a != ref_b


def test_same_chat_id_repeated_calls_idempotent() -> None:
    refs = [resolve_or_create_account_ref("999") for _ in range(5)]
    assert all(r == refs[0] for r in refs)


@pytest.mark.asyncio
async def test_send_message_calls_correct_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    resolve_or_create_account_ref("12345")
    ref = _SEALED_TG_MAPPING["12345"]

    channel = TelegramChannel(bot_token="FAKE_TOKEN")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    async def _fake_post(self: object, url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("src.channels.telegram.httpx.AsyncClient.post", _fake_post)
    result = await channel.send_message(OutboundMessage(recipient_ref=ref, text="hi", platform="telegram"))
    assert result is True
    assert "FAKE_TOKEN/sendMessage" in str(captured["url"])
    json_body = captured["kwargs"].get("json", {})
    assert isinstance(json_body, dict)
    assert json_body["chat_id"] == "12345"
    assert json_body["text"] == "hi"


@pytest.mark.asyncio
async def test_send_message_returns_false_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    resolve_or_create_account_ref("12345")
    ref = _SEALED_TG_MAPPING["12345"]

    channel = TelegramChannel(bot_token="FAKE_TOKEN")

    class FakeResponse:
        status_code = 403

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("forbidden", request=httpx.Request("POST", "http://x"), response=self)  # type: ignore[arg-type]

    async def _fake_post(self: object, url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("src.channels.telegram.httpx.AsyncClient.post", _fake_post)
    result = await channel.send_message(OutboundMessage(recipient_ref=ref, text="hi", platform="telegram"))
    assert result is False


@pytest.mark.asyncio
async def test_send_message_returns_false_for_unknown_ref() -> None:
    channel = TelegramChannel(bot_token="FAKE_TOKEN")
    result = await channel.send_message(OutboundMessage(recipient_ref="unknown-ref", text="hi", platform="telegram"))
    assert result is False


@pytest.mark.asyncio
async def test_send_ballot_formats_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    resolve_or_create_account_ref("12345")
    ref = _SEALED_TG_MAPPING["12345"]

    channel = TelegramChannel(bot_token="FAKE_TOKEN")
    sent_texts: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    async def _fake_post(self: object, url: str, **kwargs: object) -> FakeResponse:
        json_data = kwargs.get("json", {})
        if isinstance(json_data, dict):
            sent_texts.append(json_data.get("text", ""))
        return FakeResponse()

    monkeypatch.setattr("src.channels.telegram.httpx.AsyncClient.post", _fake_post)
    policies = [{"summary": "اقتصاد"}, {"summary": "آموزش"}]
    result = await channel.send_ballot(recipient_ref=ref, policies=policies)
    assert result is True
    assert len(sent_texts) == 1
    assert "1. اقتصاد" in sent_texts[0]
    assert "2. آموزش" in sent_texts[0]
    assert "صندوق رای" in sent_texts[0]


def test_raw_chat_id_not_in_unified_message() -> None:
    """Ensure the raw Telegram chat_id never appears in the UnifiedMessage."""
    channel = TelegramChannel(bot_token="fake-token")
    msg = channel.parse_webhook(VALID_PAYLOAD)
    assert msg is not None
    assert "987654321" not in msg.sender_ref
    assert "987654321" not in msg.message_id
