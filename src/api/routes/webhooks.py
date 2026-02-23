from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.channels.telegram import TelegramChannel
from src.channels.whatsapp import WhatsAppChannel
from src.config import get_settings
from src.db.connection import get_db
from src.handlers.commands import route_message

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/evolution")
async def evolution_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    if x_api_key != settings.evolution_api_key:
        raise HTTPException(status_code=401, detail="invalid api key")

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="malformed json") from exc

    channel = WhatsAppChannel(session=session)
    message = await channel.parse_webhook(payload)
    if message is None:
        return {"status": "ignored"}

    background_tasks.add_task(route_message, session=session, message=message, channel=channel)
    return {"status": "accepted"}


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=404)

    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="malformed json") from exc

    channel = TelegramChannel(
        bot_token=settings.telegram_bot_token,
        session=session,
        timeout_seconds=settings.telegram_http_timeout_seconds,
    )
    message = await channel.parse_webhook(payload)
    if message is None:
        return {"status": "ignored"}

    background_tasks.add_task(route_message, session=session, message=message, channel=channel)
    return {"status": "accepted"}
