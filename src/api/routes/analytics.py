from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.evidence import EvidenceLogEntry
from src.models.cluster import Cluster
from src.models.vote import VotingCycle

router = APIRouter()


@router.get("/clusters")
async def clusters(session: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    result = await session.execute(select(Cluster).order_by(Cluster.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": str(row.id),
            "summary": row.summary,
            "domain": row.domain.value,
            "member_count": row.member_count,
            "variance_flag": row.variance_flag,
        }
        for row in rows
    ]


@router.get("/top-policies")
async def top_policies(session: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    result = await session.execute(select(VotingCycle).where(VotingCycle.status == "tallied"))
    cycles = result.scalars().all()
    ranked: list[dict[str, object]] = []
    for cycle in cycles:
        if not cycle.results:
            continue
        for item in cycle.results:
            ranked.append(item)
    def _approval_rate(item: dict[str, object]) -> float:
        value = cast(Any, item.get("approval_rate", 0.0))
        return float(value)

    return sorted(ranked, key=_approval_rate, reverse=True)


@router.get("/evidence")
async def evidence(session: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    result = await session.execute(select(EvidenceLogEntry).order_by(EvidenceLogEntry.id.desc()).limit(200))
    rows = result.scalars().all()
    return [
        {
            "id": row.id,
            "timestamp": row.timestamp.isoformat(),
            "event_type": row.event_type,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id),
            "payload": row.payload,
            "hash": row.hash,
            "prev_hash": row.prev_hash,
        }
        for row in rows
    ]


@router.post("/evidence/verify")
async def verify_chain(entries: list[dict[str, object]]) -> dict[str, object]:
    previous = "genesis"
    for idx, entry in enumerate(entries):
        material = {
            "timestamp": entry["timestamp"],
            "event_type": entry["event_type"],
            "entity_type": entry["entity_type"],
            "entity_id": str(entry["entity_id"]).lower(),
            "payload": entry["payload"],
            "prev_hash": entry["prev_hash"],
        }
        serialized = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        expected_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        if entry["hash"] != expected_hash or entry["prev_hash"] != previous:
            return {"valid": False, "failed_index": idx}
        previous = str(entry["hash"])
    return {"valid": True, "entries_checked": len(entries)}
