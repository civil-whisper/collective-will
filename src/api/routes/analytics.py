from __future__ import annotations

import contextlib
from typing import Any, cast
from uuid import UUID

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.audit_artifacts import (
    audit_download_urls,
    bundle_contains_hash_sync,
    day_artifact_paths,
    parse_day,
    read_json_file,
    sha256_file_sync,
)
from src.config import get_settings
from src.db.connection import get_db
from src.db.evidence import VALID_EVENT_TYPES, EvidenceLogEntry, apply_visibility_tier, isoformat_z
from src.db.evidence import verify_chain as db_verify_chain
from src.models.cluster import Cluster
from src.models.endorsement import PolicyEndorsement
from src.models.policy_option import PolicyOption
from src.models.submission import PolicyCandidate, Submission
from src.models.vote import Vote, VotingCycle

router = APIRouter()


async def _read_audit_index() -> dict[str, object]:
    settings = get_settings()
    artifacts = day_artifact_paths(
        base_dir=settings.audit_bundle_output_dir,
        day_iso="2000-01-01",
    )
    index_path = artifacts.day_dir.parent / "index.json"
    index = await read_json_file(index_path)
    if index is None:
        return {
            "schema_version": 1,
            "updated_at": None,
            "days": [],
        }
    return index


def _normalize_day_or_400(day: str) -> str:
    try:
        return parse_day(day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid day") from exc


async def _audit_bundle_day_response(day_iso: str) -> dict[str, object]:
    settings = get_settings()
    artifacts = day_artifact_paths(base_dir=settings.audit_bundle_output_dir, day_iso=day_iso)
    manifest = await read_json_file(artifacts.manifest)
    if manifest is None:
        raise HTTPException(status_code=404, detail="audit bundle not found")

    bundle_exists = await artifacts.bundle.exists()
    bundle_sha256_actual = await to_thread.run_sync(sha256_file_sync, str(artifacts.bundle)) if bundle_exists else None
    manifest_bundle_sha256 = manifest.get("bundle_sha256")
    bundle_hash_matches_manifest = (
        isinstance(manifest_bundle_sha256, str)
        and bundle_sha256_actual is not None
        and manifest_bundle_sha256 == bundle_sha256_actual
    )

    timestamping = manifest.get("timestamping")
    timestamping_status = None
    verified_before = None
    bitcoin_block_height = None
    ots_proof_present = await artifacts.ots_proof.exists()
    if isinstance(timestamping, dict):
        status_value = timestamping.get("status")
        if isinstance(status_value, str):
            timestamping_status = status_value
        verified_before_value = timestamping.get("verified_before")
        if isinstance(verified_before_value, str) and verified_before_value:
            verified_before = verified_before_value
        bitcoin_block_height_value = timestamping.get("bitcoin_block_height")
        if isinstance(bitcoin_block_height_value, int):
            bitcoin_block_height = bitcoin_block_height_value

    return {
        "day_utc": day_iso,
        "entry_count": manifest.get("entry_count"),
        "daily_merkle_root": manifest.get("daily_merkle_root"),
        "bundle_sha256": manifest.get("bundle_sha256"),
        "generated_at": manifest.get("generated_at"),
        "visibility_policy_version": manifest.get("visibility_policy_version"),
        "event_catalog_version": manifest.get("event_catalog_version"),
        "timestamping": {
            "status": timestamping_status,
            "verified_before": verified_before,
            "bitcoin_block_height": bitcoin_block_height,
            "ots_proof_present": ots_proof_present,
        },
        "bundle_hash_matches_manifest": bundle_hash_matches_manifest,
        "download_urls": audit_download_urls(day_iso),
    }


@router.get("/clusters")
async def clusters(session: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    endorsement_count = (
        func.count(PolicyEndorsement.id).label("endorsement_count")
    )
    stmt = (
        select(Cluster, endorsement_count)
        .outerjoin(PolicyEndorsement, PolicyEndorsement.cluster_id == Cluster.id)
        .group_by(Cluster.id)
        .order_by(Cluster.created_at.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "id": str(row.Cluster.id),
            "policy_topic": row.Cluster.policy_topic,
            "policy_key": row.Cluster.policy_key,
            "status": row.Cluster.status,
            "summary": row.Cluster.summary,
            "member_count": row.Cluster.member_count,
            "approval_count": row.Cluster.approval_count,
            "endorsement_count": row.endorsement_count,
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

    endorsement_result = await session.execute(
        select(func.count(PolicyEndorsement.id)).where(PolicyEndorsement.cluster_id == cluster_id)
    )
    endorsement_count = int(endorsement_result.scalar_one())

    candidate_ids = list(cluster.candidate_ids)
    if candidate_ids:
        from sqlalchemy.orm import selectinload

        candidates_result = await session.execute(
            select(PolicyCandidate)
            .options(selectinload(PolicyCandidate.submission))
            .where(PolicyCandidate.id.in_(candidate_ids))
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
        "policy_topic": cluster.policy_topic,
        "policy_key": cluster.policy_key,
        "status": cluster.status,
        "summary": cluster.summary,
        "member_count": cluster.member_count,
        "approval_count": cluster.approval_count,
        "endorsement_count": endorsement_count,
        "candidates": [
            {
                "id": str(candidate.id),
                "title": candidate.title,
                "summary": candidate.summary,
                "policy_topic": candidate.policy_topic,
                "policy_key": candidate.policy_key,
                "confidence": candidate.confidence,
                "raw_text": candidate.submission.raw_text if candidate.submission else None,
                "language": candidate.submission.language if candidate.submission else None,
            }
            for candidate in ordered_candidates
        ],
    }


@router.get("/candidate/{candidate_id}/location")
async def candidate_location(
    candidate_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Return where a candidate lives: unclustered or inside a specific cluster."""
    candidate_result = await session.execute(
        select(PolicyCandidate).where(PolicyCandidate.id == candidate_id)
    )
    candidate = candidate_result.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    cluster_result = await session.execute(
        select(Cluster).where(cast(Any, Cluster.candidate_ids).any(candidate_id))
    )
    cluster = cluster_result.scalar_one_or_none()

    if cluster is not None:
        return {"status": "clustered", "cluster_id": str(cluster.id)}
    return {"status": "unclustered"}


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

    cycle_info: dict[str, object] | None = None
    if active_cycle:
        cycle_info = {
            "id": str(active_cycle.id),
            "started_at": active_cycle.started_at.isoformat(),
            "ends_at": active_cycle.ends_at.isoformat(),
            "cluster_count": len(active_cycle.cluster_ids),
        }

    return {
        "total_voters": total_voters,
        "total_submissions": total_submissions,
        "pending_submissions": pending_submissions,
        "current_cycle": str(active_cycle.id) if active_cycle else None,
        "active_cycle": cycle_info,
    }


@router.get("/unclustered")
async def unclustered(session: AsyncSession = Depends(get_db)) -> dict[str, object]:
    from sqlalchemy.orm import selectinload

    clusters_result = await session.execute(select(Cluster.candidate_ids))
    cluster_candidate_id_lists = clusters_result.scalars().all()
    clustered_candidate_ids = {
        candidate_id for candidate_ids in cluster_candidate_id_lists for candidate_id in candidate_ids
    }

    query = (
        select(PolicyCandidate)
        .options(selectinload(PolicyCandidate.submission))
        .order_by(PolicyCandidate.created_at.desc())
    )
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
                "summary": item.summary,
                "policy_topic": item.policy_topic,
                "policy_key": item.policy_key,
                "confidence": item.confidence,
                "raw_text": item.submission.raw_text if item.submission else None,
                "language": item.submission.language if item.submission else None,
            }
            for item in items
        ],
    }


@router.get("/active-ballot")
async def active_ballot(session: AsyncSession = Depends(get_db)) -> dict[str, object] | None:
    cycle_result = await session.execute(
        select(VotingCycle).where(VotingCycle.status == "active").order_by(VotingCycle.started_at.desc())
    )
    cycle = cycle_result.scalars().first()
    if cycle is None:
        return None

    voter_count_result = await session.execute(
        select(func.count(Vote.id)).where(Vote.cycle_id == cycle.id)
    )
    total_voters = int(voter_count_result.scalar_one() or 0)

    clusters_result = await session.execute(
        select(Cluster).where(Cluster.id.in_(cycle.cluster_ids))
    )
    cluster_lookup = {c.id: c for c in clusters_result.scalars().all()}

    options_result = await session.execute(
        select(PolicyOption)
        .where(PolicyOption.cluster_id.in_(cycle.cluster_ids))
        .order_by(PolicyOption.position)
    )
    options_by_cluster: dict[UUID, list[PolicyOption]] = {}
    for opt in options_result.scalars().all():
        options_by_cluster.setdefault(opt.cluster_id, []).append(opt)

    clusters_data = []
    for cid in cycle.cluster_ids:
        cluster = cluster_lookup.get(cid)
        if cluster is None:
            continue
        clusters_data.append({
            "cluster_id": str(cid),
            "summary": cluster.summary,
            "policy_topic": cluster.policy_topic,
            "ballot_question": cluster.ballot_question,
            "ballot_question_fa": cluster.ballot_question_fa,
            "options": [
                {
                    "id": str(opt.id),
                    "position": opt.position,
                    "label": opt.label,
                    "label_en": opt.label_en,
                    "description": opt.description,
                    "description_en": opt.description_en,
                }
                for opt in options_by_cluster.get(cid, [])
            ],
        })

    return {
        "id": str(cycle.id),
        "started_at": cycle.started_at.isoformat(),
        "ends_at": cycle.ends_at.isoformat(),
        "total_voters": total_voters,
        "clusters": clusters_data,
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
    query = select(EvidenceLogEntry).order_by(EvidenceLogEntry.id.desc())
    count_query = select(func.count(EvidenceLogEntry.id))

    if entity_id is not None:
        query = query.where(EvidenceLogEntry.entity_id == entity_id)
        count_query = count_query.where(EvidenceLogEntry.entity_id == entity_id)
    if event_type is not None:
        if event_type not in VALID_EVENT_TYPES:
            raise HTTPException(status_code=400, detail="invalid event_type")
        query = query.where(EvidenceLogEntry.event_type == event_type)
        count_query = count_query.where(EvidenceLogEntry.event_type == event_type)

    total_result = await session.execute(count_query)
    total = int(total_result.scalar_one())

    active_cycle_ids: set[UUID] = set()
    active_result = await session.execute(select(VotingCycle.id).where(VotingCycle.status == "active"))
    for cycle_row in active_result.all():
        active_cycle_ids.add(cycle_row[0])

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(query)
    rows = result.scalars().all()

    entries_out: list[dict[str, object]] = []
    for row in rows:
        cycle_id_raw = row.payload.get("cycle_id") if isinstance(row.payload, dict) else None
        cycle_closed = True
        if cycle_id_raw:
            with contextlib.suppress(ValueError, AttributeError):
                cycle_closed = UUID(cycle_id_raw) not in active_cycle_ids
        entries_out.append({
            "id": row.id,
            "timestamp": isoformat_z(row.timestamp),
            "event_type": row.event_type,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id),
            "payload": apply_visibility_tier(row.event_type, row.payload, cycle_closed=cycle_closed),
            "hash": row.hash,
            "prev_hash": row.prev_hash,
        })

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "entries": entries_out,
    }


@router.get("/evidence/verify")
async def verify_evidence_chain(session: AsyncSession = Depends(get_db)) -> dict[str, object]:
    valid, entries_checked = await db_verify_chain(session)
    return {"valid": valid, "entries_checked": entries_checked}


@router.get("/audit-bundles")
async def list_audit_bundles() -> dict[str, object]:
    index = await _read_audit_index()
    days_raw = index.get("days")
    days_out: list[dict[str, object]] = []
    if isinstance(days_raw, list):
        for row in days_raw:
            if not isinstance(row, dict):
                continue
            day_raw = row.get("day_utc")
            if not isinstance(day_raw, str):
                continue
            with contextlib.suppress(ValueError):
                day_iso = parse_day(day_raw)
                days_out.append({
                    "day_utc": day_iso,
                    "entry_count": row.get("entry_count"),
                    "daily_merkle_root": row.get("daily_merkle_root"),
                    "timestamping_status": row.get("timestamping_status"),
                    "ots_proof_path": row.get("ots_proof_path"),
                    "download_urls": audit_download_urls(day_iso),
                    "detail_url": f"/analytics/audit-bundles/{day_iso}",
                })
    return {
        "schema_version": index.get("schema_version", 1),
        "updated_at": index.get("updated_at"),
        "days": days_out,
    }


@router.get("/audit-bundles/{day}")
async def audit_bundle_day(day: str) -> dict[str, object]:
    day_iso = _normalize_day_or_400(day)
    return await _audit_bundle_day_response(day_iso)


@router.get("/audit-bundles/{day}/proof")
async def audit_bundle_proof(day: str, entry_hash: str = Query(min_length=1)) -> dict[str, object]:
    day_iso = _normalize_day_or_400(day)
    settings = get_settings()
    artifacts = day_artifact_paths(base_dir=settings.audit_bundle_output_dir, day_iso=day_iso)
    manifest = await read_json_file(artifacts.manifest)
    if manifest is None or not await artifacts.bundle.exists():
        raise HTTPException(status_code=404, detail="audit bundle not found")

    included_in_bundle = await to_thread.run_sync(bundle_contains_hash_sync, str(artifacts.bundle), entry_hash)
    actual_bundle_sha256 = await to_thread.run_sync(sha256_file_sync, str(artifacts.bundle))
    manifest_bundle_sha256 = manifest.get("bundle_sha256")
    bundle_hash_matches_manifest = (
        isinstance(manifest_bundle_sha256, str) and manifest_bundle_sha256 == actual_bundle_sha256
    )
    timestamping = manifest.get("timestamping")
    timestamping_status = timestamping.get("status") if isinstance(timestamping, dict) else None
    verified_before = timestamping.get("verified_before") if isinstance(timestamping, dict) else None

    return {
        "day_utc": day_iso,
        "entry_hash": entry_hash,
        "included_in_bundle": included_in_bundle,
        "bundle_hash_matches_manifest": bundle_hash_matches_manifest,
        "daily_merkle_root": manifest.get("daily_merkle_root"),
        "bundle_sha256": manifest_bundle_sha256,
        "timestamping_status": timestamping_status,
        "verified_before": verified_before,
        "download_urls": audit_download_urls(day_iso),
    }


@router.get("/audit-bundles/{day}/bundle")
async def download_audit_bundle(day: str) -> FileResponse:
    day_iso = _normalize_day_or_400(day)
    artifacts = day_artifact_paths(base_dir=get_settings().audit_bundle_output_dir, day_iso=day_iso)
    if not await artifacts.bundle.exists():
        raise HTTPException(status_code=404, detail="audit bundle not found")
    return FileResponse(str(artifacts.bundle), media_type="application/gzip", filename=artifacts.bundle.name)


@router.get("/audit-bundles/{day}/manifest")
async def download_audit_manifest(day: str) -> FileResponse:
    day_iso = _normalize_day_or_400(day)
    artifacts = day_artifact_paths(base_dir=get_settings().audit_bundle_output_dir, day_iso=day_iso)
    if not await artifacts.manifest.exists():
        raise HTTPException(status_code=404, detail="audit bundle not found")
    return FileResponse(str(artifacts.manifest), media_type="application/json", filename=artifacts.manifest.name)


@router.get("/audit-bundles/{day}/ots")
async def download_audit_ots(day: str) -> FileResponse:
    day_iso = _normalize_day_or_400(day)
    artifacts = day_artifact_paths(base_dir=get_settings().audit_bundle_output_dir, day_iso=day_iso)
    if not await artifacts.ots_proof.exists():
        raise HTTPException(status_code=404, detail="audit proof not found")
    return FileResponse(
        str(artifacts.ots_proof),
        media_type="application/octet-stream",
        filename=artifacts.ots_proof.name,
    )
