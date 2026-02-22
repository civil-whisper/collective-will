from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.channels.types import OutboundMessage
from src.channels.whatsapp import WhatsAppChannel


def _make_channel() -> WhatsAppChannel:
    return WhatsAppChannel(session=AsyncMock(), api_url="http://test:8080", api_key="key123")


@pytest.mark.asyncio
@patch("src.channels.whatsapp.get_or_create_account_ref", new_callable=AsyncMock, return_value="opaque-ref")
async def test_parse_webhook_extracts_text_and_sender_ref(mock_mapping: AsyncMock) -> None:
    channel = _make_channel()
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "989123456789@s.whatsapp.net", "fromMe": False, "id": "ABC123"},
            "message": {"conversation": "سلام"},
            "messageTimestamp": 1707000000,
        },
    }
    msg = await channel.parse_webhook(payload)
    assert msg is not None
    assert msg.text == "سلام"
    assert msg.sender_ref == "opaque-ref"
    assert msg.message_id == "ABC123"
    assert msg.raw_payload == payload
    mock_mapping.assert_called_once()


@pytest.mark.asyncio
async def test_parse_webhook_returns_none_for_status_update() -> None:
    channel = _make_channel()
    assert await channel.parse_webhook({"data": {"foo": "bar"}}) is None


@pytest.mark.asyncio
async def test_parse_webhook_returns_none_for_media_message() -> None:
    channel = _make_channel()
    payload = {
        "data": {
            "key": {"remoteJid": "98912@s.whatsapp.net", "id": "X"},
            "message": {"imageMessage": {"url": "https://example.com/img.jpg"}},
        }
    }
    assert await channel.parse_webhook(payload) is None


@pytest.mark.asyncio
@patch("src.channels.whatsapp.get_platform_id_by_ref", new_callable=AsyncMock, return_value="989123456789@s.whatsapp.net")
async def test_send_message_calls_correct_endpoint(
    mock_reverse: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = _make_channel()
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> FakeResponse:
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr("src.channels.whatsapp.httpx.AsyncClient", lambda **kw: FakeClient())
    result = await channel.send_message(OutboundMessage(recipient_ref="opaque-ref", text="hi"))
    assert result is True
    assert "test:8080/message/sendText/collective" in str(captured["url"])
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    body = kwargs.get("json")
    assert isinstance(body, dict)
    assert body.get("number") == "989123456789@s.whatsapp.net"


@pytest.mark.asyncio
@patch("src.channels.whatsapp.get_platform_id_by_ref", new_callable=AsyncMock, return_value="989123456789@s.whatsapp.net")
async def test_send_message_returns_false_on_http_error(
    mock_reverse: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    channel = _make_channel()

    class FakeResponse:
        status_code = 500

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("fail", request=httpx.Request("POST", "http://x"), response=self)  # type: ignore[arg-type]

    class FakeClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("src.channels.whatsapp.httpx.AsyncClient", lambda **kw: FakeClient())
    result = await channel.send_message(OutboundMessage(recipient_ref="opaque-ref", text="hi"))
    assert result is False


@pytest.mark.asyncio
@patch("src.channels.whatsapp.get_platform_id_by_ref", new_callable=AsyncMock, return_value="989123456789@s.whatsapp.net")
async def test_send_ballot_formats_correctly(
    mock_reverse: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel = _make_channel()
    sent_texts: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> FakeResponse:
            json_data = kwargs.get("json", {})
            if isinstance(json_data, dict):
                sent_texts.append(json_data.get("text", ""))
            return FakeResponse()

    monkeypatch.setattr("src.channels.whatsapp.httpx.AsyncClient", lambda **kw: FakeClient())
    policies = [{"summary": "اقتصاد"}, {"summary": "آموزش"}]
    result = await channel.send_ballot(recipient_ref="opaque-ref", policies=policies)
    assert result is True
    assert len(sent_texts) == 1
    assert "1. اقتصاد" in sent_texts[0]
    assert "2. آموزش" in sent_texts[0]


@pytest.mark.asyncio
@patch("src.channels.whatsapp.get_platform_id_by_ref", new_callable=AsyncMock, return_value=None)
async def test_send_message_returns_false_without_reverse_mapping(mock_reverse: AsyncMock) -> None:
    channel = _make_channel()
    result = await channel.send_message(OutboundMessage(recipient_ref="unknown-ref", text="hi"))
    assert result is False


@pytest.mark.asyncio
@patch("src.channels.whatsapp.get_or_create_account_ref", new_callable=AsyncMock, return_value="stable-ref")
async def test_parse_webhook_mapping_stability(mock_mapping: AsyncMock) -> None:
    channel = _make_channel()
    payload = {
        "data": {
            "key": {"remoteJid": "98912@s.whatsapp.net", "id": "M1"},
            "message": {"conversation": "hello"},
        }
    }
    first = await channel.parse_webhook(payload)
    second = await channel.parse_webhook(payload)
    assert first is not None
    assert second is not None
    assert first.sender_ref == second.sender_ref
