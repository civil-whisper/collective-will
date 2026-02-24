from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.db.connection import Base


class SchedulerHeartbeat(Base):
    __tablename__ = "scheduler_heartbeat"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    detail: Mapped[str | None] = mapped_column(String(256), nullable=True)


HEARTBEAT_SINGLETON_ID = UUID("00000000-0000-0000-0000-000000000001")


async def upsert_heartbeat(
    session: AsyncSession,
    *,
    status: str = "ok",
    detail: str | None = None,
) -> None:
    now = datetime.now(UTC)
    row = await session.get(SchedulerHeartbeat, HEARTBEAT_SINGLETON_ID)
    if row is None:
        row = SchedulerHeartbeat(
            id=HEARTBEAT_SINGLETON_ID,
            last_run_at=now,
            status=status,
            detail=detail,
        )
        session.add(row)
    else:
        row.last_run_at = now
        row.status = status
        row.detail = detail
    await session.commit()


async def get_heartbeat(session: AsyncSession) -> SchedulerHeartbeat | None:
    result = await session.execute(
        select(SchedulerHeartbeat).where(SchedulerHeartbeat.id == HEARTBEAT_SINGLETON_ID)
    )
    return result.scalar_one_or_none()
