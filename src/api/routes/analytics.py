from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.evidence import EvidenceLogEntry, isoformat_z
from src.db.evidence import verify_chain as db_verify_chain
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate, Submission
from src.models.vote import Vote, VotingCycle

PII_PAYLOAD_KEYS = {"user_id", "email", "account_ref", "wa_id"}


def strip_evidence_pii(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in PII_PAYLOAD_KEYS}

router = APIRouter()


@router.get("/clusters")
async def clusters(session: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    result = await session.execute(select(Cluster).order_by(Cluster.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": str(row.id),
            "summary": row.summary,
            "domain": row.domain.value if hasattr(row.domain, "value") else row.domain,
            "member_count": row.member_count,
            "approval_count": row.approval_count,
            "variance_flag": row.variance_flag,
        }
        for row in rows
    ]


@router.get("/clusters/{cluster_id}")
async def cluster_detail(
    cluster_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    cluster_result = await session.execute(select(Cluster).where(Cluster.id == cluster_id))
    cluster = cluster_result.scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=404, detail="cluster_not_found")

    candidate_ids = list(cluster.candidate_ids)
    if candidate_ids:
        candidates_result = await session.execute(
            select(PolicyCandidate).where(PolicyCandidate.id.in_(candidate_ids))
        )
        db_candidates = candidates_result.scalars().all()
    else:
        db_candidates = []

    candidates_by_id = {candidate.id: candidate for candidate in db_candidates}
    ordered_candidates = [
        candidates_by_id[candidate_id] for candidate_id in candidate_ids if candidate_id in candidates_by_id
    ]

    return {
        "id": str(cluster.id),
        "summary": cluster.summary,
        "summary_en": cluster.summary_en,
        "domain": cluster.domain.value if hasattr(cluster.domain, "value") else cluster.domain,
        "member_count": cluster.member_count,
        "approval_count": cluster.approval_count,
        "variance_flag": cluster.variance_flag,
        "grouping_rationale": None,
        "candidates": [
            {
                "id": str(candidate.id),
                "title": candidate.title,
                "title_en": candidate.title_en,
                "summary": candidate.summary,
                "summary_en": candidate.summary_en,
                "domain": (
                    candidate.domain.value if hasattr(candidate.domain, "value") else candidate.domain
                ),
                "confidence": candidate.confidence,
            }
            for candidate in ordered_candidates
        ],
    }


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_db)) -> dict[str, object]:
    total_voters_result = await session.execute(select(func.count(func.distinct(Vote.user_id))))
    total_voters = int(total_voters_result.scalar_one() or 0)

    total_submissions_result = await session.execute(select(func.count(Submission.id)))
    total_submissions = int(total_submissions_result.scalar_one() or 0)

    pending_submissions_result = await session.execute(
        select(func.count(Submission.id)).where(Submission.status == "pending")
    )
    pending_submissions = int(pending_submissions_result.scalar_one() or 0)

    cycle_result = await session.execute(
        select(VotingCycle).where(VotingCycle.status == "active").order_by(VotingCycle.started_at.desc())
    )
    active_cycle = cycle_result.scalars().first()

    return {
        "total_voters": total_voters,
        "total_submissions": total_submissions,
        "pending_submissions": pending_submissions,
        "current_cycle": str(active_cycle.id) if active_cycle else None,
    }


@router.get("/unclustered")
async def unclustered(session: AsyncSession = Depends(get_db)) -> dict[str, object]:
    clusters_result = await session.execute(select(Cluster.candidate_ids))
    cluster_candidate_id_lists = clusters_result.scalars().all()
    clustered_candidate_ids = {
        candidate_id for candidate_ids in cluster_candidate_id_lists for candidate_id in candidate_ids
    }

    query = select(PolicyCandidate).order_by(PolicyCandidate.created_at.desc())
    count_query = select(func.count(PolicyCandidate.id))
    if clustered_candidate_ids:
        query = query.where(~PolicyCandidate.id.in_(clustered_candidate_ids))
        count_query = count_query.where(~PolicyCandidate.id.in_(clustered_candidate_ids))

    total_result = await session.execute(count_query)
    total = int(total_result.scalar_one() or 0)

    items_result = await session.execute(query.limit(50))
    items = items_result.scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "title_en": item.title_en,
                "summary": item.summary,
                "summary_en": item.summary_en,
                "domain": item.domain.value if hasattr(item.domain, "value") else item.domain,
                "confidence": item.confidence,
            }
            for item in items
        ],
    }


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
async def evidence(
    session: AsyncSession = Depends(get_db),
    entity_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    query = select(EvidenceLogEntry).order_by(EvidenceLogEntry.id.asc())
    count_query = select(func.count(EvidenceLogEntry.id))

    if entity_id is not None:
        query = query.where(EvidenceLogEntry.entity_id == entity_id)
        count_query = count_query.where(EvidenceLogEntry.entity_id == entity_id)
    if event_type is not None:
        query = query.where(EvidenceLogEntry.event_type == event_type)
        count_query = count_query.where(EvidenceLogEntry.event_type == event_type)

    total_result = await session.execute(count_query)
    total = int(total_result.scalar_one())

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(query)
    rows = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "entries": [
            {
                "id": row.id,
                "timestamp": isoformat_z(row.timestamp),
                "event_type": row.event_type,
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id),
                "payload": strip_evidence_pii(row.payload),
                "hash": row.hash,
                "prev_hash": row.prev_hash,
            }
            for row in rows
        ],
    }


@router.get("/evidence/verify")
async def verify_evidence_chain(session: AsyncSession = Depends(get_db)) -> dict[str, object]:
    valid, entries_checked = await db_verify_chain(session)
    return {"valid": valid, "entries_checked": entries_checked}
