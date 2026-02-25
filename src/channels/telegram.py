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


class TelegramChannel(BaseChannel):
    def __init__(self, bot_token: str, session: AsyncSession, timeout_seconds: float | None = None) -> None:
        settings = get_settings()
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.client = httpx.AsyncClient(timeout=timeout_seconds or settings.telegram_http_timeout_seconds)
        self._session = session

    async def parse_webhook(self, payload: dict[str, Any]) -> UnifiedMessage | None:
        callback = payload.get("callback_query")
        if callback is not None:
            return await self._parse_callback_query(callback)

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

        sender_ref = await get_or_create_account_ref(self._session, "telegram", chat_id)
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

    async def _parse_callback_query(self, callback: dict[str, Any]) -> UnifiedMessage | None:
        msg = callback.get("message", {})
        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        if not chat_id:
            return None

        sender_ref = await get_or_create_account_ref(self._session, "telegram", chat_id)
        message_id = str(msg.get("message_id", ""))
        date_ts = msg.get("date")
        timestamp = datetime.fromtimestamp(int(date_ts), tz=UTC) if date_ts else datetime.now(UTC)

        return UnifiedMessage(
            sender_ref=sender_ref,
            text="",
            platform="telegram",
            timestamp=timestamp,
            message_id=message_id,
            raw_payload={"callback_query": callback},
            callback_data=callback.get("data", ""),
            callback_query_id=str(callback.get("id", "")),
        )

    async def send_message(self, message: OutboundMessage) -> bool:
        chat_id = await get_platform_id_by_ref(self._session, message.recipient_ref)
        if chat_id is None:
            logger.error("No chat_id mapping for account_ref %s", message.recipient_ref)
            return False

        url = f"{self.api_url}/sendMessage"
        body: dict[str, Any] = {"chat_id": chat_id, "text": message.text}
        if message.reply_markup:
            body["reply_markup"] = message.reply_markup
        try:
            response = await self.client.post(url, json=body)
            response.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.exception("Failed to send Telegram message to account_ref %s", message.recipient_ref)
            return False

    async def answer_callback(self, callback_query_id: str, text: str | None = None) -> bool:
        url = f"{self.api_url}/answerCallbackQuery"
        body: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            body["text"] = text
        try:
            response = await self.client.post(url, json=body)
            response.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.exception("Failed to answer callback query %s", callback_query_id)
            return False

    async def edit_message_markup(
        self, recipient_ref: str, message_id: str, reply_markup: dict[str, Any]
    ) -> bool:
        chat_id = await get_platform_id_by_ref(self._session, recipient_ref)
        if chat_id is None:
            logger.error("No chat_id mapping for account_ref %s", recipient_ref)
            return False

        url = f"{self.api_url}/editMessageReplyMarkup"
        body: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "reply_markup": reply_markup,
        }
        try:
            response = await self.client.post(url, json=body)
            response.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.RequestError):
            logger.exception("Failed to edit message markup for account_ref %s", recipient_ref)
            return False
