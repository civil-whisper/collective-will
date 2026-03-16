from __future__ import annotations

import hashlib
import hmac
import inspect
import json
from dataclasses import dataclass, field
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

PII_PAYLOAD_KEYS = {"user_id", "email", "account_ref", "wa_id"}


@dataclass(frozen=True, slots=True)
class EventSpec:
    """Metadata for one auditable event type."""

    description: str
    entity_type: str
    generates_receipt: bool = False
    public_fields: frozenset[str] = field(default_factory=frozenset)
    delayed_fields: frozenset[str] = field(default_factory=frozenset)


EVENT_CATALOG: dict[str, EventSpec] = {
    # --- Submission lifecycle ---
    "submission_received": EventSpec(
        description="Submission recorded",
        entity_type="submission",
        public_fields=frozenset({"submission_id", "language", "status", "hash", "raw_text", "reason_code"}),
    ),
    "submission_not_eligible": EventSpec(
        description="Submission rejected: user not eligible",
        entity_type="user",
        public_fields=frozenset({"reason_code"}),
    ),
    "submission_rate_limited": EventSpec(
        description="Submission rejected: rate limit",
        entity_type="user",
        public_fields=frozenset({"reason_code", "limit_type"}),
    ),
    "submission_rejected_not_policy": EventSpec(
        description="Submission rejected: not a policy proposal",
        entity_type="submission",
        public_fields=frozenset({"submission_id", "rejection_reason", "model_version", "prompt_version"}),
    ),
    # --- Candidate lifecycle ---
    "candidate_created": EventSpec(
        description="Policy candidate created from submission",
        entity_type="submission",
        public_fields=frozenset({
            "submission_id", "title", "summary", "stance",
            "policy_topic", "policy_key", "actor_scope", "action_mechanism",
            "target_scope", "ballot_readiness", "ballot_readiness_reason",
            "confidence", "model_version", "prompt_version",
        }),
    ),
    "candidate_classified": EventSpec(
        description="Candidate classified with semantic identity",
        entity_type="candidate",
        public_fields=frozenset({
            "candidate_id", "submission_id", "policy_key", "policy_topic",
            "actor_scope", "action_mechanism", "target_scope",
            "ballot_readiness", "ballot_readiness_reason", "confidence",
            "model_version", "prompt_version",
        }),
    ),
    "candidate_rekeyed": EventSpec(
        description="Candidate key or semantic identity changed",
        entity_type="candidate",
        public_fields=frozenset({
            "candidate_id", "submission_id", "stage",
            "old_policy_key", "new_policy_key",
            "old_policy_topic", "new_policy_topic",
            "old_ballot_readiness", "new_ballot_readiness",
            "reason_code",
        }),
    ),
    # --- Cluster lifecycle ---
    "cluster_created": EventSpec(
        description="New policy cluster formed",
        entity_type="cluster",
        public_fields=frozenset({"cluster_id", "policy_key", "policy_topic", "member_count"}),
    ),
    "cluster_updated": EventSpec(
        description="Cluster membership changed",
        entity_type="cluster",
        public_fields=frozenset({"cluster_id", "policy_key", "old_member_count", "new_member_count"}),
    ),
    "cluster_merged": EventSpec(
        description="Clusters merged during normalization",
        entity_type="cluster",
        public_fields=frozenset({"survivor_key", "merged_key", "merged_cluster_id", "new_member_count"}),
    ),
    "ballot_question_generated": EventSpec(
        description="Ballot question generated for cluster",
        entity_type="cluster",
        public_fields=frozenset({"policy_key", "ballot_question", "member_count", "model_version"}),
    ),
    "policy_options_generated": EventSpec(
        description="Stance options generated for cluster",
        entity_type="cluster",
        public_fields=frozenset({"cluster_id", "option_count", "labels", "model_version"}),
    ),
    "refinement_draft_generated": EventSpec(
        description="Refinement draft generated for cluster",
        entity_type="cluster",
        public_fields=frozenset({
            "cluster_id", "policy_key", "refinement_draft", "refinement_confidence",
            "requires_clarification", "notes", "model_version",
        }),
    ),
    # --- Endorsement lifecycle ---
    "policy_endorsed": EventSpec(
        description="User endorsed a policy cluster",
        entity_type="policy_endorsement",
        generates_receipt=True,
        public_fields=frozenset({"cluster_id"}),
    ),
    "endorsement_not_eligible": EventSpec(
        description="Endorsement rejected: user not eligible",
        entity_type="user",
        public_fields=frozenset({"reason_code"}),
    ),
    # --- Voting lifecycle ---
    "vote_cast": EventSpec(
        description="Vote recorded in active cycle",
        entity_type="vote",
        generates_receipt=True,
        public_fields=frozenset({"cycle_id"}),
        delayed_fields=frozenset({"approved_cluster_ids", "selections"}),
    ),
    "vote_not_eligible": EventSpec(
        description="Vote rejected: user not eligible",
        entity_type="user",
        public_fields=frozenset({"reason_code", "cycle_id"}),
    ),
    "vote_change_limit_reached": EventSpec(
        description="Vote change rejected: limit reached",
        entity_type="user",
        public_fields=frozenset({"cycle_id"}),
    ),
    "cycle_opened": EventSpec(
        description="Voting cycle opened",
        entity_type="voting_cycle",
        public_fields=frozenset({
            "cycle_id", "cluster_ids", "starts_at", "ends_at", "cycle_duration_hours",
        }),
    ),
    "cycle_closed": EventSpec(
        description="Voting cycle closed and tallied",
        entity_type="voting_cycle",
        public_fields=frozenset({"total_voters", "results"}),
    ),
    # --- Identity ---
    "user_verified": EventSpec(
        description="User identity verified",
        entity_type="user",
        public_fields=frozenset({"method"}),
    ),
    # --- Disputes ---
    "dispute_escalated": EventSpec(
        description="Dispute escalated to ensemble",
        entity_type="submission",
        public_fields=frozenset({
            "threshold", "primary_model", "primary_confidence",
            "ensemble_models", "selected_model", "selected_confidence",
        }),
    ),
    "dispute_resolved": EventSpec(
        description="Dispute resolved by automated review",
        entity_type="submission",
        public_fields=frozenset({
            "submission_id", "candidate_id", "escalated", "confidence",
            "model_version", "resolved_title", "resolved_summary", "resolution_seconds",
        }),
    ),
    "dispute_metrics_recorded": EventSpec(
        description="Dispute metrics checkpoint recorded",
        entity_type="system",
        public_fields=frozenset({"period", "total_disputes", "escalation_rate", "avg_resolution_seconds"}),
    ),
    "dispute_tuning_recommended": EventSpec(
        description="Model/policy tuning recommended based on dispute metrics",
        entity_type="system",
        public_fields=frozenset({"reason", "metrics"}),
    ),
    # --- Anchoring ---
    "anchor_computed": EventSpec(
        description="Daily Merkle root computed",
        entity_type="daily_anchor",
        public_fields=frozenset({"day", "merkle_root", "entry_count"}),
    ),
    "anchor_publish_attempted": EventSpec(
        description="External timestamping attempted",
        entity_type="daily_anchor",
        public_fields=frozenset({"day", "merkle_root", "provider"}),
    ),
    "anchor_publish_succeeded": EventSpec(
        description="External timestamping succeeded",
        entity_type="daily_anchor",
        public_fields=frozenset({"day", "merkle_root", "provider", "status", "ots_proof_path"}),
    ),
    "anchor_publish_failed": EventSpec(
        description="External timestamping failed",
        entity_type="daily_anchor",
        public_fields=frozenset({"day", "merkle_root", "provider", "status", "error_type"}),
    ),
    "audit_bundle_generated": EventSpec(
        description="Daily redacted audit bundle generated",
        entity_type="daily_anchor",
        public_fields=frozenset({"day", "entry_count", "bundle_sha256", "storage_path"}),
    ),
    "audit_bundle_publish_succeeded": EventSpec(
        description="Daily redacted audit bundle publish succeeded",
        entity_type="daily_anchor",
        public_fields=frozenset({"day", "bundle_sha256", "manifest_path", "index_path"}),
    ),
    "audit_bundle_publish_failed": EventSpec(
        description="Daily redacted audit bundle publish failed",
        entity_type="daily_anchor",
        public_fields=frozenset({"day", "bundle_sha256", "error_type"}),
    ),
    # --- Pipeline degradation / fallback ---
    "submission_deferred_to_batch": EventSpec(
        description="Inline processing failed; submission deferred to batch",
        entity_type="submission",
        public_fields=frozenset({"submission_id", "error_type", "step"}),
    ),
    "candidate_parse_repaired": EventSpec(
        description="Malformed LLM output was repaired before use",
        entity_type="submission",
        public_fields=frozenset({"submission_id", "repair_method", "model_version"}),
    ),
    "normalization_step_failed": EventSpec(
        description="Normalization LLM call failed for an embedding cluster",
        entity_type="cluster",
        public_fields=frozenset({"policy_keys", "error_type", "step"}),
    ),
    "ballot_generation_failed": EventSpec(
        description="Ballot question generation failed for a cluster",
        entity_type="cluster",
        public_fields=frozenset({"cluster_id", "policy_key", "error_type"}),
    ),
    "policy_options_fallback_used": EventSpec(
        description="Generic fallback options used instead of LLM-generated options",
        entity_type="cluster",
        public_fields=frozenset({"cluster_id", "policy_key", "error_type"}),
    ),
    "dispute_ensemble_member_failed": EventSpec(
        description="A dispute ensemble model failed during resolution",
        entity_type="submission",
        public_fields=frozenset({"model", "error_type"}),
    ),
    # --- Voice ---
    "voice_enrolled": EventSpec(
        description="Voice enrollment completed",
        entity_type="user",
        public_fields=frozenset({"phrase_count", "model_version"}),
    ),
    "voice_enroll_phrase_rejected": EventSpec(
        description="Voice enrollment phrase rejected",
        entity_type="user",
        public_fields=frozenset({"phrase_id", "reject_reason"}),
    ),
    "voice_verified": EventSpec(
        description="Voice verification completed",
        entity_type="user",
        public_fields=frozenset({"result", "phrase_id", "reject_reason"}),
    ),
}

VALID_EVENT_TYPES = set(EVENT_CATALOG.keys())


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


def generate_receipt_token(entry_hash: str, signing_key: str) -> str:
    """Create an HMAC receipt token binding an evidence entry to a signing key.

    Users receive this token as proof their action was included in the chain.
    Verification is stateless: recompute HMAC and compare.
    """
    return hmac.new(
        signing_key.encode("utf-8"), entry_hash.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_receipt_token(entry_hash: str, signing_key: str, token: str) -> bool:
    expected = generate_receipt_token(entry_hash, signing_key)
    return hmac.compare_digest(expected, token)


def strip_evidence_pii(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip PII keys from evidence payload for public display."""
    result: dict[str, Any] = {}
    for k, v in payload.items():
        if k in PII_PAYLOAD_KEYS:
            continue
        if isinstance(v, dict):
            result[k] = strip_evidence_pii(v)
        elif isinstance(v, list):
            result[k] = [strip_evidence_pii(item) if isinstance(item, dict) else item for item in v]
        else:
            result[k] = v
    return result


def apply_visibility_tier(
    event_type: str,
    payload: dict[str, Any],
    *,
    cycle_closed: bool = False,
) -> dict[str, Any]:
    """Apply visibility-tier filtering on top of PII stripping.

    - Strips PII recursively.
    - Removes delayed fields when cycle is still active.
    """
    cleaned = strip_evidence_pii(payload)
    spec = EVENT_CATALOG.get(event_type)
    if spec and spec.delayed_fields and not cycle_closed:
        cleaned = {k: v for k, v in cleaned.items() if k not in spec.delayed_fields}
    return cleaned
