from __future__ import annotations

import hashlib
import inspect
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from src.db.connection import Base

GENESIS_PREV_HASH = "genesis"
EVIDENCE_CHAIN_LOCK_KEY = 704281913
VALID_EVENT_TYPES = {
    "submission_received",
    "candidate_created",
    "cluster_created",
    "cluster_updated",
    "policy_endorsed",
    "vote_cast",
    "cycle_opened",
    "cycle_closed",
    "user_verified",
    "dispute_escalated",
    "dispute_resolved",
    "dispute_metrics_recorded",
    "dispute_tuning_recommended",
    "anchor_computed",
}


class EvidenceLogEntry(Base):
    __tablename__ = "evidence_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)


def canonical_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def isoformat_z(ts: datetime) -> str:
    dt = ts.astimezone(UTC)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def compute_entry_hash(
    *,
    timestamp_iso: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    prev_hash: str,
) -> str:
    material = {
        "timestamp": timestamp_iso,
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id.lower(),
        "payload": payload,
        "prev_hash": prev_hash,
    }
    serialized = canonical_json(material)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def append_evidence(
    session: AsyncSession,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    payload: dict[str, Any],
) -> EvidenceLogEntry:
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event_type: {event_type}")

    async with session.begin_nested():
        # Serialize append operations so concurrent writers cannot reuse the same prev_hash.
        bind = session.get_bind()
        if inspect.isawaitable(bind):
            bind = await bind
        dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
        if dialect_name == "postgresql":
            await session.execute(select(func.pg_advisory_xact_lock(EVIDENCE_CHAIN_LOCK_KEY)))

        last_result = await session.execute(
            select(EvidenceLogEntry).order_by(EvidenceLogEntry.id.desc()).limit(1).with_for_update()
        )
        last_entry = last_result.scalar_one_or_none()
        prev_hash = last_entry.hash if last_entry else GENESIS_PREV_HASH
        timestamp = datetime.now(UTC)
        entry_hash = compute_entry_hash(
            timestamp_iso=isoformat_z(timestamp),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id),
            payload=payload,
            prev_hash=prev_hash,
        )
        entry = EvidenceLogEntry(
            timestamp=timestamp,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            hash=entry_hash,
            prev_hash=prev_hash,
        )
        session.add(entry)
        await session.flush()
        await session.refresh(entry)
        return entry


async def verify_chain(session: AsyncSession) -> tuple[bool, int]:
    result = await session.execute(select(EvidenceLogEntry).order_by(EvidenceLogEntry.id.asc()))
    entries = list(result.scalars().all())
    prev_hash = GENESIS_PREV_HASH

    for index, entry in enumerate(entries):
        expected = compute_entry_hash(
            timestamp_iso=isoformat_z(entry.timestamp),
            event_type=entry.event_type,
            entity_type=entry.entity_type,
            entity_id=str(entry.entity_id),
            payload=entry.payload,
            prev_hash=entry.prev_hash,
        )
        if entry.hash != expected:
            return (False, index + 1)
        if entry.prev_hash != prev_hash:
            return (False, index + 1)
        prev_hash = entry.hash

    return (True, len(entries))
