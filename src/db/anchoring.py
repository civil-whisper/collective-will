from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy import Date, DateTime, String, and_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.config import Settings
from src.db.connection import Base
from src.db.evidence import EvidenceLogEntry, append_evidence


class DailyAnchor(Base):
    __tablename__ = "daily_anchors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    published_receipt: Mapped[str | None] = mapped_column(String, nullable=True)
    anchor_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


def _pair_hash(left: str, right: str) -> str:
    payload = f"{left}{right}".encode()
    return hashlib.sha256(payload).hexdigest()


def compute_merkle_root(leaves: list[str]) -> str:
    if not leaves:
        raise ValueError("Cannot compute Merkle root for empty leaves")
    level = leaves[:]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level: list[str] = []
        for idx in range(0, len(level), 2):
            next_level.append(_pair_hash(level[idx], level[idx + 1]))
        level = next_level
    return level[0]


async def compute_daily_merkle_root(session: AsyncSession, day: date) -> str | None:
    start = datetime.combine(day, time.min).replace(tzinfo=UTC)
    end = start + timedelta(days=1)
    result = await session.execute(
        select(EvidenceLogEntry)
        .where(and_(EvidenceLogEntry.timestamp >= start, EvidenceLogEntry.timestamp < end))
        .order_by(EvidenceLogEntry.id.asc())
    )
    entries = list(result.scalars().all())
    if not entries:
        return None

    root = compute_merkle_root([entry.hash for entry in entries])
    existing = await session.execute(select(DailyAnchor).where(DailyAnchor.day == day))
    anchor = existing.scalar_one_or_none()
    if anchor is None:
        anchor = DailyAnchor(day=day, merkle_root=root, anchor_metadata={"entry_count": len(entries)})
        session.add(anchor)
        await session.flush()
        await append_evidence(
            session=session,
            event_type="cluster_updated",
            entity_type="daily_anchor",
            entity_id=entries[-1].entity_id,
            payload={"day": day.isoformat(), "merkle_root": root, "entry_count": len(entries)},
        )
    return root


async def publish_daily_merkle_root(
    root: str,
    day: date,
    settings: Settings,
    session: AsyncSession | None = None,
) -> str | None:
    if not settings.witness_publish_enabled:
        return None
    if not settings.witness_api_key:
        raise ValueError("WITNESS_API_KEY is required when publication is enabled")

    payload = {"day": day.isoformat(), "root": root}
    headers = {"Authorization": f"Bearer {settings.witness_api_key}"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(f"{settings.witness_api_url}/anchors", json=payload, headers=headers)
        response.raise_for_status()
        receipt_value = response.json().get("id")
        receipt = str(receipt_value) if receipt_value is not None else None

    if session is not None:
        result = await session.execute(select(DailyAnchor).where(DailyAnchor.day == day))
        anchor = result.scalar_one_or_none()
        if anchor is not None:
            anchor.published_receipt = receipt
    return receipt
