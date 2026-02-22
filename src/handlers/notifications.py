from __future__ import annotations

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage


async def send_status_message(*, channel: BaseChannel, recipient_ref: str, text: str) -> None:
    await channel.send_message(OutboundMessage(recipient_ref=recipient_ref, text=text))
