from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.db.connection import Base


class VerificationToken(Base):
    __tablename__ = "verification_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    token: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    token_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


async def store_token(
    session: AsyncSession,
    *,
    token: str,
    email: str,
    token_type: str,
    expiry_minutes: int,
) -> VerificationToken:
    expires_at = datetime.now(UTC) + timedelta(minutes=expiry_minutes)
    vt = VerificationToken(
        token=token,
        email=email,
        token_type=token_type,
        expires_at=expires_at,
    )
    session.add(vt)
    await session.flush()
    return vt


async def lookup_token(
    session: AsyncSession, token: str, token_type: str
) -> tuple[str, bool] | None:
    """Look up a token. Returns (email, is_expired) or None if not found/already used."""
    result = await session.execute(
        select(VerificationToken).where(
            VerificationToken.token == token,
            VerificationToken.token_type == token_type,
            VerificationToken.used.is_(False),
        )
    )
    vt = result.scalar_one_or_none()
    if vt is None:
        return None

    is_expired = datetime.now(UTC) > vt.expires_at
    return vt.email, is_expired


async def consume_token(session: AsyncSession, token: str, token_type: str) -> bool:
    """Mark a token as used. Returns True if found and marked."""
    result = await session.execute(
        select(VerificationToken).where(
            VerificationToken.token == token,
            VerificationToken.token_type == token_type,
            VerificationToken.used.is_(False),
        )
    )
    vt = result.scalar_one_or_none()
    if vt is None:
        return False
    vt.used = True
    return True
