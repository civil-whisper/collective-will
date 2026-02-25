from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.base import BaseChannel
from src.channels.types import OutboundMessage, UnifiedMessage
from src.config import get_settings
from src.db.sealed_mapping import get_or_create_account_ref, get_platform_id_by_ref

logger = logging.getLogger(__name__)


class WhatsAppChannel(BaseChannel):
    def __init__(
        self,
        session: AsyncSession,
        api_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self.api_url = api_url or settings.evolution_api_url
        self.api_key = api_key or settings.evolution_api_key
        self.http_timeout_seconds = settings.whatsapp_http_timeout_seconds
        self._session = session

    async def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        data = payload.get("data", {})
        message_data = data.get("message", {})
        text = message_data.get("conversation")
        key = data.get("key", {})
        sender_wa_id = key.get("remoteJid")
        message_id = key.get("id", "")

        if not text or not sender_wa_id:
            return None

        sender_ref = await get_or_create_account_ref(self._session, "whatsapp", sender_wa_id)
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
        wa_id = await get_platform_id_by_ref(self._session, message.recipient_ref)
        if wa_id is None:
            logger.error("No wa_id mapping for account_ref %s", message.recipient_ref)
            return False
        url = f"{self.api_url}/message/sendText/collective"
        headers = {"apikey": self.api_key}
        body = {"number": wa_id, "text": message.text}
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.exception("Failed to send message to %s", message.recipient_ref)
            return False

