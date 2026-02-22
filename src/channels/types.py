from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UnifiedMessage(BaseModel):
    """Normalized incoming message from any platform."""

    text: str
    sender_ref: str
    platform: Literal["whatsapp"] = "whatsapp"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message_id: str
    raw_payload: dict[str, Any] | None = None


class OutboundMessage(BaseModel):
    """Message to send to a user."""

    recipient_ref: str
    text: str
    platform: Literal["whatsapp"] = "whatsapp"
