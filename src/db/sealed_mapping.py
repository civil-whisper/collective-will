from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.db.connection import Base


class SealedAccountMapping(Base):
    __tablename__ = "sealed_account_mappings"
    __table_args__ = (
        UniqueConstraint("platform", "platform_id", name="uq_sealed_platform_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_id: Mapped[str] = mapped_column(String(256), nullable=False)
    account_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


async def get_or_create_account_ref(
    session: AsyncSession, platform: str, platform_id: str
) -> str:
    """Resolve an existing opaque account ref or create a new one."""
    result = await session.execute(
        select(SealedAccountMapping.account_ref).where(
            SealedAccountMapping.platform == platform,
            SealedAccountMapping.platform_id == platform_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    account_ref = str(uuid4())
    mapping = SealedAccountMapping(
        platform=platform,
        platform_id=platform_id,
        account_ref=account_ref,
    )
    session.add(mapping)
    await session.flush()
    return account_ref


async def get_platform_id_by_ref(
    session: AsyncSession, account_ref: str
) -> str | None:
    """Reverse-lookup: get the raw platform ID from an opaque account ref."""
    result = await session.execute(
        select(SealedAccountMapping.platform_id).where(
            SealedAccountMapping.account_ref == account_ref,
        )
    )
    return result.scalar_one_or_none()
