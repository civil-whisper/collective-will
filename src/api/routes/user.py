from __future__ import annotations

from typing import Annotated
from uuid import UUID

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.audit_artifacts import (
    audit_download_urls,
    bundle_contains_hash_sync,
    day_artifact_paths,
    read_json_file,
    sha256_file_sync,
)
from src.api.authn import require_user_from_bearer
from src.api.rate_limit import enforce_dispute_rate_limit
from src.config import get_settings
from src.db.connection import get_db
from src.db.evidence import EVENT_CATALOG, EvidenceLogEntry, generate_receipt_token, isoformat_z
from src.handlers.disputes import resolve_submission_dispute
from src.models.submission import Submission
from src.models.user import User
from src.models.vote import Vote

router = APIRouter()

def _derive_receipt_status(
    *,
    receipt_valid: bool,
    entry_found: bool,
    bundle_exists: bool,
    manifest_exists: bool,
    included_in_public_bundle: bool,
    bundle_hash_matches_manifest: bool,
    ots_proof_present: bool,
    ots_verified: bool,
) -> str:
    if not receipt_valid or not entry_found:
        return "failed"
    if ots_verified:
        return "verified"
    if ots_proof_present:
        return "timestamped"
    if included_in_public_bundle and bundle_hash_matches_manifest:
        return "published"
    if (bundle_exists or manifest_exists) and (not included_in_public_bundle or not bundle_hash_matches_manifest):
        return "failed"
    return "recorded"


@router.get("/dashboard/submissions")
async def list_submissions(
    user: Annotated[User, Depends(require_user_from_bearer)],
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    result = await session.execute(
        select(Submission).where(Submission.user_id == user.id).order_by(Submission.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        {"id": str(row.id), "raw_text": row.raw_text, "status": row.status, "hash": row.hash}
        for row in rows
    ]


@router.get("/dashboard/votes")
async def list_votes(
    user: Annotated[User, Depends(require_user_from_bearer)],
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    result = await session.execute(select(Vote).where(Vote.user_id == user.id).order_by(Vote.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": str(row.id),
            "cycle_id": str(row.cycle_id),
            "approved_cluster_ids": [str(cluster_id) for cluster_id in row.approved_cluster_ids],
        }
        for row in rows
    ]


@router.get("/dashboard/receipts")
async def list_receipts(
    user: Annotated[User, Depends(require_user_from_bearer)],
    session: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    """Return the authenticated user's evidence entries with receipt tokens.

    Only events whose payloads contain the user's ID are returned. Each
    entry includes a receipt_token (HMAC) the user can present externally
    to prove their action was recorded in the chain.
    """
    settings = get_settings()
    uid_str = str(user.id)

    receipt_event_types = {et for et, spec in EVENT_CATALOG.items() if spec.generates_receipt}
    query = (
        select(EvidenceLogEntry)
        .where(EvidenceLogEntry.event_type.in_(receipt_event_types))
        .order_by(EvidenceLogEntry.id.desc())
    )
    result = await session.execute(query)
    all_entries = result.scalars().all()

    user_entries = [e for e in all_entries if isinstance(e.payload, dict) and e.payload.get("user_id") == uid_str]
    total = len(user_entries)
    start = (page - 1) * per_page
    page_entries = user_entries[start : start + per_page]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "entries": [
            {
                "id": entry.id,
                "timestamp": isoformat_z(entry.timestamp),
                "event_type": entry.event_type,
                "entity_type": entry.entity_type,
                "entity_id": str(entry.entity_id),
                "payload": entry.payload,
                "hash": entry.hash,
                "prev_hash": entry.prev_hash,
                "receipt_token": generate_receipt_token(entry.hash, settings.web_access_token_secret),
            }
            for entry in page_entries
        ],
    }


@router.get("/dashboard/receipts/{entry_hash}/verify")
async def verify_receipt(
    entry_hash: str,
    user: Annotated[User, Depends(require_user_from_bearer)],
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    receipt_event_types = {et for et, spec in EVENT_CATALOG.items() if spec.generates_receipt}

    result = await session.execute(
        select(EvidenceLogEntry)
        .where(EvidenceLogEntry.hash == entry_hash)
        .where(EvidenceLogEntry.event_type.in_(receipt_event_types))
        .limit(1)
    )
    entry = result.scalar_one_or_none()
    uid_str = str(user.id)
    if entry is None or not isinstance(entry.payload, dict) or entry.payload.get("user_id") != uid_str:
        raise HTTPException(status_code=404, detail="receipt not found")

    day_iso = entry.timestamp.date().isoformat()
    artifacts = day_artifact_paths(
        base_dir=settings.audit_bundle_output_dir,
        day_iso=day_iso,
    )
    bundle_exists = await artifacts.bundle.exists()
    manifest_exists = await artifacts.manifest.exists()

    included_in_public_bundle = False
    if bundle_exists:
        included_in_public_bundle = await to_thread.run_sync(
            bundle_contains_hash_sync,
            str(artifacts.bundle),
            entry.hash,
        )

    bundle_hash_matches_manifest = False
    ots_proof_present = False
    ots_verified = False
    verified_before: str | None = None
    manifest = await read_json_file(artifacts.manifest)
    if manifest is not None:
        actual_bundle_sha256 = None
        if bundle_exists:
            actual_bundle_sha256 = await to_thread.run_sync(sha256_file_sync, str(artifacts.bundle))
        manifest_bundle_sha256 = manifest.get("bundle_sha256")
        if isinstance(manifest_bundle_sha256, str) and actual_bundle_sha256 is not None:
            bundle_hash_matches_manifest = manifest_bundle_sha256 == actual_bundle_sha256

        timestamping = manifest.get("timestamping")
        if isinstance(timestamping, dict):
            ots_path_value = timestamping.get("ots_proof_path")
            if isinstance(ots_path_value, str) and ots_path_value:
                ots_proof_present = await artifacts.ots_proof.exists()
            verified_before_value = timestamping.get("verified_before")
            if isinstance(verified_before_value, str) and verified_before_value:
                verified_before = verified_before_value
            ots_verified = timestamping.get("status") == "verified"

    receipt_valid = EVENT_CATALOG[entry.event_type].generates_receipt
    status = _derive_receipt_status(
        receipt_valid=receipt_valid,
        entry_found=True,
        bundle_exists=bundle_exists,
        manifest_exists=manifest_exists,
        included_in_public_bundle=included_in_public_bundle,
        bundle_hash_matches_manifest=bundle_hash_matches_manifest,
        ots_proof_present=ots_proof_present,
        ots_verified=ots_verified,
    )

    return {
        "status": status,
        "receipt_valid": receipt_valid,
        "entry_found": True,
        "bundle_day": day_iso,
        "included_in_public_bundle": included_in_public_bundle,
        "bundle_hash_matches_manifest": bundle_hash_matches_manifest,
        "ots_proof_present": ots_proof_present,
        "ots_verified": ots_verified,
        "verified_before": verified_before,
        "download_urls": audit_download_urls(day_iso),
    }


@router.post("/dashboard/disputes/{submission_id}")
async def open_dispute(
    submission_id: str,
    user: Annotated[User, Depends(require_user_from_bearer)],
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    enforce_dispute_rate_limit(str(user.id))
    try:
        submission_uuid = UUID(submission_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid submission id") from exc
    result = await session.execute(
        select(Submission).where(Submission.id == submission_uuid, Submission.user_id == user.id)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="submission not found")

    await resolve_submission_dispute(session=session, submission=submission)
    return {"status": "under_automated_review"}
