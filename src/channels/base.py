from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.channels.types import OutboundMessage, UnifiedMessage


class BaseChannel(ABC):
    """Abstract interface for messaging platforms."""

    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> bool:
        """Send a message. Returns True if sent successfully."""
        ...

    @abstractmethod
    async def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        """Parse incoming webhook payload into UnifiedMessage.
        Returns None if payload is not a user text message or callback query."""
        ...

    async def answer_callback(self, callback_query_id: str, text: str | None = None) -> bool:
        """Acknowledge an inline-keyboard callback tap. Platforms without
        callback support return False by default."""
        return False

    async def edit_message_markup(
        self, recipient_ref: str, message_id: str, reply_markup: dict[str, Any]
    ) -> bool:
        """Edit the inline keyboard on an existing message. Platforms without
        inline keyboard support return False by default."""
        return False
