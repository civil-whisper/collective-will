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
    def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        """Parse incoming webhook payload into UnifiedMessage.
        Returns None if payload is not a user text message."""
        ...

    @abstractmethod
    async def send_ballot(self, recipient_ref: str, policies: list[dict[str, Any]]) -> bool:
        """Send a formatted voting ballot to a user."""
        ...
