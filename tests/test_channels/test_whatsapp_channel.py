from __future__ import annotations

import pytest

from src.channels.types import OutboundMessage
from src.channels.whatsapp import (
    _REVERSE_WA_MAPPING,
    _SEALED_WA_MAPPING,
    WhatsAppChannel,
    resolve_or_create_account_ref,
)


@pytest.fixture(autouse=True)
def _clear_mapping() -> None:
    _SEALED_WA_MAPPING.clear()
    _REVERSE_WA_MAPPING.clear()


def test_parse_webhook_extracts_text_and_sender_ref() -> None:
    channel = WhatsAppChannel()
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "989123456789@s.whatsapp.net", "fromMe": False, "id": "ABC123"},
            "message": {"conversation": "سلام"},
            "messageTimestamp": 1707000000,
        },
    }
    msg = channel.parse_webhook(payload)
    assert msg is not None
    assert msg.text == "سلام"
    assert msg.sender_ref != "989123456789@s.whatsapp.net"
    assert msg.message_id == "ABC123"
    assert msg.raw_payload == payload


def test_parse_webhook_returns_none_for_status_update() -> None:
    channel = WhatsAppChannel()
    assert channel.parse_webhook({"data": {"foo": "bar"}}) is None


def test_parse_webhook_returns_none_for_media_message() -> None:
    channel = WhatsAppChannel()
    payload = {
        "data": {
            "key": {"remoteJid": "98912@s.whatsapp.net", "id": "X"},
            "message": {"imageMessage": {"url": "https://example.com/img.jpg"}},
        }
    }
    assert channel.parse_webhook(payload) is None


def test_resolve_or_create_returns_existing_ref() -> None:
    ref1 = resolve_or_create_account_ref("wa123")
    ref2 = resolve_or_create_account_ref("wa123")
    assert ref1 == ref2


def test_resolve_or_create_new_uuid_for_unseen() -> None:
    ref = resolve_or_create_account_ref("new-id")
    assert len(ref) == 36  # UUID format


def test_different_wa_ids_produce_different_refs() -> None:
    ref_a = resolve_or_create_account_ref("a@s.whatsapp.net")
    ref_b = resolve_or_create_account_ref("b@s.whatsapp.net")
    assert ref_a != ref_b


@pytest.mark.asyncio
async def test_send_message_calls_correct_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = WhatsAppChannel(api_url="http://test:8080", api_key="key123")
    captured: dict[str, object] = {}
    ref = resolve_or_create_account_ref("989123456789@s.whatsapp.net")

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
    result = await channel.send_message(OutboundMessage(recipient_ref=ref, text="hi"))
    assert result is True
    assert "test:8080/message/sendText/collective" in str(captured["url"])
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    body = kwargs.get("json")
    assert isinstance(body, dict)
    assert body.get("number") == "989123456789@s.whatsapp.net"


@pytest.mark.asyncio
async def test_send_message_returns_false_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    channel = WhatsAppChannel(api_url="http://test:8080", api_key="key123")
    ref = resolve_or_create_account_ref("989123456789@s.whatsapp.net")

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
    result = await channel.send_message(OutboundMessage(recipient_ref=ref, text="hi"))
    assert result is False


@pytest.mark.asyncio
async def test_send_ballot_formats_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = WhatsAppChannel(api_url="http://test:8080", api_key="key123")
    sent_texts: list[str] = []
    ref = resolve_or_create_account_ref("989123456789@s.whatsapp.net")

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
    result = await channel.send_ballot(recipient_ref=ref, policies=policies)
    assert result is True
    assert len(sent_texts) == 1
    assert "1. اقتصاد" in sent_texts[0]
    assert "2. آموزش" in sent_texts[0]


@pytest.mark.asyncio
async def test_send_message_returns_false_without_reverse_mapping() -> None:
    channel = WhatsAppChannel(api_url="http://test:8080", api_key="key123")
    result = await channel.send_message(OutboundMessage(recipient_ref="unknown-ref", text="hi"))
    assert result is False


def test_parse_webhook_mapping_stability() -> None:
    channel = WhatsAppChannel()
    payload = {
        "data": {
            "key": {"remoteJid": "98912@s.whatsapp.net", "id": "M1"},
            "message": {"conversation": "hello"},
        }
    }
    first = channel.parse_webhook(payload)
    second = channel.parse_webhook(payload)
    assert first is not None
    assert second is not None
    assert first.sender_ref == second.sender_ref
