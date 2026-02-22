from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.config import get_settings

logger = logging.getLogger(__name__)

_SEALED_WA_MAPPING: dict[str, str] = {}
_REVERSE_WA_MAPPING: dict[str, str] = {}


def resolve_or_create_account_ref(wa_id: str) -> str:
    """Resolve an existing account ref or create a new opaque one for the given wa_id."""
    existing = _SEALED_WA_MAPPING.get(wa_id)
    if existing:
        return existing
    account_ref = str(uuid4())
    _SEALED_WA_MAPPING[wa_id] = account_ref
    _REVERSE_WA_MAPPING[account_ref] = wa_id
    return account_ref


def _reverse_lookup(account_ref: str) -> str | None:
    return _REVERSE_WA_MAPPING.get(account_ref)


class WhatsAppChannel(BaseChannel):
    def __init__(self, api_url: str | None = None, api_key: str | None = None) -> None:
        settings = get_settings()
        self.api_url = api_url or settings.evolution_api_url
        self.api_key = api_key or settings.evolution_api_key

    def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        data = payload.get("data", {})
        message_data = data.get("message", {})
        text = message_data.get("conversation")
        key = data.get("key", {})
        sender_wa_id = key.get("remoteJid")
        message_id = key.get("id", "")

        if not text or not sender_wa_id:
            return None

        sender_ref = resolve_or_create_account_ref(sender_wa_id)
        ts_raw = data.get("messageTimestamp")
        timestamp = datetime.fromtimestamp(int(ts_raw), tz=UTC) if ts_raw else datetime.now(UTC)

        return UnifiedMessage(
            sender_ref=sender_ref,
            text=text,
            platform="whatsapp",
            timestamp=timestamp,
            message_id=message_id,
            raw_payload=payload,
        )

    async def send_message(self, message: OutboundMessage) -> bool:
        wa_id = _reverse_lookup(message.recipient_ref)
        if wa_id is None:
            logger.error("No wa_id mapping for account_ref %s", message.recipient_ref)
            return False
        url = f"{self.api_url}/message/sendText/collective"
        headers = {"apikey": self.api_key}
        body = {"number": wa_id, "text": message.text}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.exception("Failed to send message to %s", message.recipient_ref)
            return False

    async def send_ballot(self, recipient_ref: str, policies: list[dict[str, Any]]) -> bool:
        lines = ["🗳️ صندوق رای باز است!\n", "این هفته، این سیاست‌ها مطرح شدند:\n"]
        for i, p in enumerate(policies, 1):
            lines.append(f"{i}. {p.get('summary', '')}")
        lines.append("\nبرای رای دادن، شماره‌های موردنظر خود را بفرستید.")
        lines.append('مثال: 1, 3')
        lines.append('\nبرای انصراف: "انصراف" بفرستید')
        ballot_text = "\n".join(lines)
        return await self.send_message(OutboundMessage(recipient_ref=recipient_ref, text=ballot_text))
