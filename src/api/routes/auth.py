from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.handlers.identity import subscribe_email, verify_magic_link

router = APIRouter()


class SubscribeRequest(BaseModel):
    email: EmailStr
    locale: str = "fa"
    requester_ip: str
    messaging_account_ref: str


@router.post("/subscribe")
async def subscribe(
    payload: SubscribeRequest,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    user, token = await subscribe_email(
        session=session,
        email=str(payload.email),
        locale=payload.locale,
        requester_ip=payload.requester_ip,
        messaging_account_ref=payload.messaging_account_ref,
    )
    if user is None:
        raise HTTPException(status_code=429, detail=token or "signup blocked")
    return {"status": "pending_verification", "token": token or ""}


@router.post("/verify/{token}")
async def verify(
    token: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    ok, status = await verify_magic_link(session=session, token=token)
    if not ok:
        raise HTTPException(status_code=400, detail=status)
    return {"status": status}
