from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage


class FakeChannel(BaseChannel):
    def __init__(self) -> None:
        self.sent: list[OutboundMessage] = []

    def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        return UnifiedMessage(sender_ref="x", text=payload["text"], message_id="fake-1")

    async def send_message(self, message: OutboundMessage) -> bool:
        self.sent.append(message)
        return True

    async def send_ballot(self, recipient_ref: str, policies: list[dict[str, Any]]) -> bool:
        return True


def test_unified_message_validates_correct_input() -> None:
    msg = UnifiedMessage(sender_ref="abc", text="hello", message_id="msg-1")
    assert msg.platform == "whatsapp"
    assert msg.sender_ref == "abc"
    assert msg.text == "hello"
    assert msg.message_id == "msg-1"
    assert msg.raw_payload is None
    assert isinstance(msg.timestamp, datetime)


def test_unified_message_rejects_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        UnifiedMessage(sender_ref="abc")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        UnifiedMessage(text="hello", message_id="m1")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        UnifiedMessage(sender_ref="abc", text="hello")  # type: ignore[call-arg]


def test_unified_message_rejects_invalid_platform() -> None:
    with pytest.raises(ValidationError):
        UnifiedMessage(
            sender_ref="abc",
            text="hello",
            message_id="m1",
            platform="signal",
        )


def test_unified_message_accepts_telegram_platform() -> None:
    msg = UnifiedMessage(sender_ref="abc", text="hello", message_id="m1", platform="telegram")
    assert msg.platform == "telegram"


def test_outbound_message_validates_correct_input() -> None:
    msg = OutboundMessage(recipient_ref="ref-1", text="reply")
    assert msg.platform == "whatsapp"
    assert msg.recipient_ref == "ref-1"
    assert msg.text == "reply"


def test_base_channel_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseChannel()  # type: ignore[abstract]


def test_concrete_subclass_can_be_instantiated() -> None:
    channel = FakeChannel()
    assert isinstance(channel, BaseChannel)


@pytest.mark.asyncio
async def test_fake_channel_works_without_whatsapp_imports() -> None:
    channel = FakeChannel()
    inbound = channel.parse_webhook({"text": "hello"})
    assert inbound is not None
    assert inbound.text == "hello"
    result = await channel.send_message(OutboundMessage(recipient_ref="x", text="ok"))
    assert result is True
    assert len(channel.sent) == 1
