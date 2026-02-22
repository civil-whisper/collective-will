from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage

logger = logging.getLogger(__name__)

_SEALED_TG_MAPPING: dict[str, str] = {}
_REVERSE_TG_MAPPING: dict[str, str] = {}


def resolve_or_create_account_ref(chat_id: str) -> str:
    """Resolve an existing account ref or create a new opaque one for a Telegram chat_id."""
    existing = _SEALED_TG_MAPPING.get(chat_id)
    if existing:
        return existing
    account_ref = str(uuid4())
    _SEALED_TG_MAPPING[chat_id] = account_ref
    _REVERSE_TG_MAPPING[account_ref] = chat_id
    return account_ref


def _reverse_lookup(account_ref: str) -> str | None:
    return _REVERSE_TG_MAPPING.get(account_ref)


class TelegramChannel(BaseChannel):
    def __init__(self, bot_token: str) -> None:
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.client = httpx.AsyncClient(timeout=30.0)

    def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        message = payload.get("message")
        if message is None:
            return None

        text = message.get("text")
        if not text:
            return None

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            return None

        sender_ref = resolve_or_create_account_ref(chat_id)
        message_id = str(message.get("message_id", ""))
        date_ts = message.get("date")
        timestamp = datetime.fromtimestamp(int(date_ts), tz=UTC) if date_ts else datetime.now(UTC)

        return UnifiedMessage(
            sender_ref=sender_ref,
            text=text,
            platform="telegram",
            timestamp=timestamp,
            message_id=message_id,
            raw_payload=payload,
        )

    async def send_message(self, message: OutboundMessage) -> bool:
        chat_id = _reverse_lookup(message.recipient_ref)
        if chat_id is None:
            logger.error("No chat_id mapping for account_ref %s", message.recipient_ref)
            return False

        url = f"{self.api_url}/sendMessage"
        body = {"chat_id": chat_id, "text": message.text}
        try:
            response = await self.client.post(url, json=body)
            response.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.exception("Failed to send Telegram message to account_ref %s", message.recipient_ref)
            return False

    async def send_ballot(self, recipient_ref: str, policies: list[dict[str, Any]]) -> bool:
        lines = ["🗳️ صندوق رای باز است!\n", "این هفته، این سیاست‌ها مطرح شدند:\n"]
        for i, p in enumerate(policies, 1):
            lines.append(f"{i}. {p.get('summary', '')}")
        lines.append("\nبرای رای دادن، شماره‌های موردنظر خود را بفرستید.")
        lines.append("مثال: 1, 3")
        lines.append('\nبرای انصراف: "انصراف" بفرستید')
        ballot_text = "\n".join(lines)
        return await self.send_message(
            OutboundMessage(recipient_ref=recipient_ref, text=ballot_text, platform="telegram")
        )
