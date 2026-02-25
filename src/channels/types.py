from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UnifiedMessage(BaseModel):
    """Normalized incoming message from any platform."""

    text: str
    sender_ref: str
    platform: Literal["whatsapp", "telegram"] = "whatsapp"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message_id: str
    raw_payload: dict[str, Any] | None = None
    callback_data: str | None = None
    callback_query_id: str | None = None


class OutboundMessage(BaseModel):
    """Message to send to a user."""

    recipient_ref: str
    text: str
    platform: Literal["whatsapp", "telegram"] = "whatsapp"
    reply_markup: dict[str, Any] | None = None
