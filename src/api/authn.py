from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.models.user import User
from src.security.web_auth import verify_web_access_token


def resolve_email_from_bearer(*, authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    email = verify_web_access_token(token=token)
    if email is None:
        raise HTTPException(status_code=401, detail="invalid bearer token")
    return email


def require_email_from_bearer(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    return resolve_email_from_bearer(authorization=authorization)


async def require_user_from_bearer(
    session: Annotated[AsyncSession, Depends(get_db)],
    email: Annotated[str, Depends(require_email_from_bearer)],
) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return user
