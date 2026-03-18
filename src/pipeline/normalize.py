"""Phase 2: Hybrid embedding + LLM policy key normalization.

Uses embedding cosine similarity to discover semantically similar candidates
across ALL topics, then asks the LLM (with full summaries) to produce a
canonical key mapping.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter

logger = logging.getLogger(__name__)

COSINE_SIMILARITY_THRESHOLD = 0.55

_REMAP_SYSTEM_PROMPT = (
    "You are a policy analyst for a democratic deliberation platform. "
    "Your job is to review a group of semantically similar policy submissions "
    "and decide how they should be grouped into ballot-level policy keys."
)

_REUSE_REVIEW_SYSTEM_PROMPT = (
    "You are a policy analyst for a democratic deliberation platform. "
    "Your job is to review candidates that currently share the same provisional policy key "
    "and decide whether each new candidate truly belongs under that ballot-level proposition "
    "or should receive a different key."
)

_REMAP_PROMPT_TEMPLATE = """\
These policy submissions were identified as semantically similar based on \
their content. Each currently has a policy_key assigned.

Review ALL their summaries and produce a canonical key mapping.
You may keep existing keys, merge several into one, or create a better key \
name if none of the existing ones fit well.

Submissions:
{submissions_block}

Rules:
- Group submissions that address the SAME specific ballot-level issue under \
ONE canonical key.
- Do NOT merge genuinely different sub-issues that need separate votes.
- Do NOT merge submissions when the actor, mechanism, or target differs, even \
if they share a broad political goal.
- The canonical key should be stance-neutral, descriptive, and use \
lowercase-with-hyphens.
- You may create a new key name if no existing key captures the group well.
- Keys that should stay separate can map to themselves.

Reply with ONLY a raw JSON object (no markdown):
{{"key_mapping": {{"old-key-1": "canonical-key", "old-key-2": "canonical-key", \
"old-key-3": "old-key-3"}}}}
"""

_REUSE_REVIEW_PROMPT_TEMPLATE = """\
These candidates currently share the provisional policy key "{policy_key}".

Existing open-cluster members for this key:
{existing_block}

New candidates to evaluate:
{new_block}

Rules:
- Reuse the existing key only when the candidate expresses the SAME ballot-level proposition.
- If assigning the candidate to the existing key would materially change ballot wording,
  option sets, or refinement output, assign a new key.
- Do not create a new key for minor wording differences that still represent the same proposition.
- New keys must be stance-neutral, descriptive, and lowercase-with-hyphens.
- `policy_topic` should be a short browsing label, also lowercase-with-hyphens.
- Return decisions for NEW candidates only.

Reply with ONLY raw JSON (no markdown):
{{
  "decisions": [
    {{
      "candidate_id": "<new-candidate-id>",
      "reuse_existing_key": true,
      "policy_key": "{policy_key}",
      "policy_topic": "<topic>",
      "reason_code": "same_proposition"
    }}
  ]
}}
"""


@dataclass(slots=True)
class KeyMerge:
    topic: str
    merged_keys: list[str]
    survivor_key: str


def _build_submissions_block(
    entries: list[dict[str, Any]],
) -> str:
    """Build a numbered list of submissions with full summaries for the LLM."""
    lines: list[str] = []
    for i, entry in enumerate(entries, 1):
        lines.append(
            f'  {i}. [key: "{entry["key"]}", ui_topic: "{entry["topic"]}", '
            f'actor: "{entry["actor_scope"]}", mechanism: "{entry["action_mechanism"]}", '
            f'target: "{entry["target_scope"]}", readiness: "{entry["ballot_readiness"]}", '
            f'{entry["count"]} submissions]'
        )
        lines.append(f"     {entry['summary']}")
    return "\n".join(lines)


def _has_compound_shape(candidate: Any) -> bool:
    return any(
        str(flag).strip().lower() == "compound_submission"
        for flag in getattr(candidate, "ambiguity_flags", [])
    )


def _same_key_group_needs_revalidation(candidates: list[Any]) -> bool:
    if len(candidates) < 2:
        return False

    non_unclear_actors = {
        str(candidate.actor_scope)
        for candidate in candidates
        if str(candidate.actor_scope) != "unclear"
    }
    non_unclear_mechanisms = {
        str(candidate.action_mechanism) for candidate in candidates if str(candidate.action_mechanism) != "unclear"
    }
    non_unclear_targets = {
        str(candidate.target_scope)
        for candidate in candidates
        if str(candidate.target_scope) != "unclear"
    }
    readiness_values = {str(candidate.ballot_readiness) for candidate in candidates}
    compound_values = {_has_compound_shape(candidate) for candidate in candidates}

    return (
        len(non_unclear_actors) > 1
        or len(non_unclear_mechanisms) > 1
        or len(non_unclear_targets) > 1
        or ("ballot-ready" in readiness_values and len(readiness_values) > 1)
        or len(compound_values) > 1
    )


def _build_revalidation_candidate_block(candidates: list[Any]) -> str:
    if not candidates:
        return "(none)"

    lines: list[str] = []
    for candidate in candidates:
        flags = ", ".join(str(flag) for flag in getattr(candidate, "ambiguity_flags", [])) or "none"
        lines.append(
            "- "
            f'[candidate_id="{candidate.id}"; actor="{candidate.actor_scope}"; '
            f'mechanism="{candidate.action_mechanism}"; target="{candidate.target_scope}"; '
            f'readiness="{candidate.ballot_readiness}"; flags="{flags}"] '
            f"{candidate.title}: {candidate.summary}"
        )
    return "\n".join(lines)


def _parse_reuse_review_response(raw: str) -> dict[str, dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        last = text.rfind("```")
        text = text[nl + 1:last].strip()
    if text and text[0] not in ("{", "["):
        start = text.find("{")
        if start != -1:
            text = text[start:]
    payload = json.loads(text)
    decisions = payload.get("decisions", [])
    return {
        str(item["candidate_id"]): {
            "reuse_existing_key": bool(item.get("reuse_existing_key", True)),
            "policy_key": str(item.get("policy_key", "")),
            "policy_topic": str(item.get("policy_topic", "")),
            "reason_code": str(item.get("reason_code", "")) or "same_key_revalidation",
        }
        for item in decisions
        if isinstance(item, dict) and item.get("candidate_id") is not None
    }


async def review_same_key_reuse(
    *,
    policy_key: str,
    existing_members: list[Any],
    new_candidates: list[Any],
    llm_router: LLMRouter,
) -> dict[str, dict[str, Any]]:
    prompt = _REUSE_REVIEW_PROMPT_TEMPLATE.format(
        policy_key=policy_key,
        existing_block=_build_revalidation_candidate_block(existing_members),
        new_block=_build_revalidation_candidate_block(new_candidates),
    )
    completion = await llm_router.complete(
        tier="english_reasoning",
        prompt=prompt,
        system_prompt=_REUSE_REVIEW_SYSTEM_PROMPT,
        temperature=0.0,
    )
    return _parse_reuse_review_response(completion.text)


async def revalidate_candidate_key_reuse(
    *,
    session: AsyncSession,
    new_candidates: list[PolicyCandidate],
    llm_router: LLMRouter,
) -> int:
    keys = sorted({candidate.policy_key for candidate in new_candidates if candidate.policy_key != "unassigned"})
    if not keys:
        return 0

    lanes = {candidate.submission_lane for candidate in new_candidates}
    cluster_result = await session.execute(
        select(Cluster).where(
            Cluster.status == "open",
            Cluster.policy_key.in_(keys),
            Cluster.submission_lane.in_(lanes),
        )
    )
    open_clusters = {cluster.policy_key: cluster for cluster in cluster_result.scalars().all()}

    existing_ids = {
        candidate_id
        for cluster in open_clusters.values()
        for candidate_id in cluster.candidate_ids
    }
    existing_candidates_by_id: dict[Any, PolicyCandidate] = {}
    if existing_ids:
        existing_result = await session.execute(select(PolicyCandidate).where(PolicyCandidate.id.in_(existing_ids)))
        existing_candidates_by_id = {candidate.id: candidate for candidate in existing_result.scalars().all()}

    updated = 0
    for key in keys:
        key_new_candidates = [candidate for candidate in new_candidates if candidate.policy_key == key]
        cluster = open_clusters.get(key)
        existing_members = []
        if cluster is not None:
            existing_members = [
                existing_candidates_by_id[candidate_id]
                for candidate_id in cluster.candidate_ids
                if candidate_id in existing_candidates_by_id
            ]
        combined = [*existing_members, *key_new_candidates]
        if not _same_key_group_needs_revalidation(combined):
            continue

        decisions = await review_same_key_reuse(
            policy_key=key,
            existing_members=existing_members,
            new_candidates=key_new_candidates,
            llm_router=llm_router,
        )
        for candidate in key_new_candidates:
            decision = decisions.get(str(candidate.id))
            if decision is None or decision.get("reuse_existing_key", True):
                continue

            new_policy_key = str(decision.get("policy_key", "")).strip()
            new_policy_topic = str(decision.get("policy_topic", "")).strip()
            if not new_policy_key or new_policy_key == candidate.policy_key:
                continue

            old_policy_key = candidate.policy_key
            old_policy_topic = candidate.policy_topic
            candidate.policy_key = new_policy_key
            if new_policy_topic:
                candidate.policy_topic = new_policy_topic

            await append_evidence(
                session=session,
                event_type="candidate_rekeyed",
                entity_type="candidate",
                entity_id=candidate.id,
                payload={
                    "candidate_id": str(candidate.id),
                    "submission_id": str(candidate.submission_id),
                    "stage": "same_key_revalidation",
                    "old_policy_key": old_policy_key,
                    "new_policy_key": candidate.policy_key,
                    "old_policy_topic": old_policy_topic,
                    "new_policy_topic": candidate.policy_topic,
                    "old_ballot_readiness": candidate.ballot_readiness,
                    "new_ballot_readiness": candidate.ballot_readiness,
                    "reason_code": str(decision.get("reason_code", "same_key_revalidation")),
                },
            )
            updated += 1
    return updated


def _parse_remap_response(raw: str) -> dict[str, str]:
    """Parse LLM response into {old_key: canonical_key} mapping."""
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        last = text.rfind("```")
        text = text[nl + 1 : last].strip()
    if text and text[0] not in ("{", "["):
        start = text.find("{")
        if start != -1:
            text = text[start:]
    data = json.loads(text)
    return dict(data.get("key_mapping", {}))


def _cluster_by_embedding(
    embeddings: np.ndarray,
    threshold: float = COSINE_SIMILARITY_THRESHOLD,
) -> list[int]:
    """Agglomerative clustering on cosine distance. Returns cluster labels."""
    if len(embeddings) < 2:
        return list(range(len(embeddings)))
    distances = pdist(embeddings, metric="cosine")
    distances = np.clip(distances, 0, 2)
    Z = linkage(distances, method="average")
    labels = fcluster(Z, t=1.0 - threshold, criterion="distance")
    return [int(lbl) for lbl in labels]


async def normalize_policy_keys(
    *,
    session: AsyncSession,
    llm_router: LLMRouter,
) -> list[KeyMerge]:
    """Hybrid normalization: embedding similarity + LLM key remapping.

    1. Load all non-unassigned candidates with embeddings
    2. Cluster by cosine similarity across ALL topics
    3. For each cluster containing 2+ distinct policy_keys,
       send ALL summaries to LLM for canonical key mapping
    4. Execute merges from the mapping
    """
    candidates_result = await session.execute(
        select(PolicyCandidate)
        .where(PolicyCandidate.policy_key != "unassigned")
        .where(PolicyCandidate.embedding.isnot(None))
    )
    candidates = list(candidates_result.scalars().all())

    if len(candidates) < 2:
        return []

    embeddings = np.array(
        [c.embedding for c in candidates], dtype=np.float64,
    )
    labels = _cluster_by_embedding(embeddings)

    groups: dict[int, list[PolicyCandidate]] = defaultdict(list)
    for candidate, label in zip(candidates, labels, strict=True):
        groups[label].append(candidate)

    all_merges: list[KeyMerge] = []
    for _label, members in groups.items():
        distinct_lanes = {c.submission_lane for c in members}
        if len(distinct_lanes) > 1:
            continue

        distinct_keys = {c.policy_key for c in members}
        if len(distinct_keys) < 2:
            continue

        entries = _build_entries_for_cluster(members)
        if not _entries_are_merge_compatible(entries):
            logger.info(
                "Skipping normalization merge for keys %s due to incompatible semantics",
                distinct_keys,
            )
            continue
        submissions_block = _build_submissions_block(entries)
        prompt = _REMAP_PROMPT_TEMPLATE.format(
            submissions_block=submissions_block,
        )

        try:
            completion = await llm_router.complete(
                tier="english_reasoning",
                prompt=prompt,
                system_prompt=_REMAP_SYSTEM_PROMPT,
                temperature=0.0,
            )
            key_mapping = _parse_remap_response(completion.text)
        except Exception as exc:
            logger.exception(
                "Normalization LLM call failed for embedding cluster with keys %s",
                distinct_keys,
            )
            representative = next(iter(members))
            await append_evidence(
                session=session,
                event_type="normalization_step_failed",
                entity_type="cluster",
                entity_id=representative.id,
                payload={
                    "policy_keys": sorted(distinct_keys),
                    "error_type": type(exc).__name__,
                    "step": "llm_remap",
                },
            )
            continue

        group_lane = next(iter({c.submission_lane for c in members}))
        merges = _extract_merges_from_mapping(key_mapping, distinct_keys)
        for survivor_key, merged_keys in merges.items():
            await execute_key_merge(
                session=session,
                survivor_key=survivor_key,
                merged_keys=merged_keys,
                submission_lane=group_lane,
            )
            survivor_topic = _topic_for_key(members, survivor_key)
            all_merges.append(
                KeyMerge(
                    topic=survivor_topic,
                    merged_keys=merged_keys,
                    survivor_key=survivor_key,
                )
            )

    return all_merges


def _build_entries_for_cluster(
    members: list[PolicyCandidate],
) -> list[dict[str, Any]]:
    """Build per-key entries with full summaries for the LLM prompt."""
    key_data: dict[str, dict[str, Any]] = {}
    for c in members:
        pk = c.policy_key
        if pk not in key_data:
            key_data[pk] = {
                "key": pk,
                "topic": c.policy_topic,
                "count": 1,
                "summaries": [c.summary or ""],
                "actor_scope": c.actor_scope,
                "action_mechanism": c.action_mechanism,
                "target_scope": c.target_scope,
                "ballot_readiness": c.ballot_readiness,
            }
        else:
            key_data[pk]["count"] += 1
            key_data[pk]["summaries"].append(c.summary or "")

    entries: list[dict[str, Any]] = []
    for kd in sorted(key_data.values(), key=lambda x: -x["count"]):
        combined = " | ".join(
            s.replace("\n", " ") for s in kd["summaries"] if s
        )
        entries.append({
            "key": kd["key"],
            "topic": kd["topic"],
            "count": kd["count"],
            "summary": combined,
            "actor_scope": kd["actor_scope"],
            "action_mechanism": kd["action_mechanism"],
            "target_scope": kd["target_scope"],
            "ballot_readiness": kd["ballot_readiness"],
        })
    return entries


def _entries_are_merge_compatible(entries: list[dict[str, Any]]) -> bool:
    if not entries:
        return False

    actor_scopes = {str(entry.get("actor_scope", "unclear")) for entry in entries}
    mechanisms = {str(entry.get("action_mechanism", "unclear")) for entry in entries}
    targets = {str(entry.get("target_scope", "unclear")) for entry in entries}
    readiness_values = {str(entry.get("ballot_readiness", "discussion-only")) for entry in entries}

    non_unclear_actors = actor_scopes - {"unclear"}
    non_unclear_mechanisms = mechanisms - {"unclear"}
    non_unclear_targets = targets - {"unclear"}
    if len(non_unclear_actors) > 1 or len(non_unclear_mechanisms) > 1 or len(non_unclear_targets) > 1:
        return False
    return "ballot-ready" not in readiness_values or len(readiness_values) <= 1


def _extract_merges_from_mapping(
    key_mapping: dict[str, str],
    valid_keys: set[str],
) -> dict[str, list[str]]:
    """Convert {old_key: canonical_key} into {canonical_key: [merged_keys]}."""
    groups: dict[str, list[str]] = defaultdict(list)
    for old_key, canonical_key in key_mapping.items():
        if old_key not in valid_keys:
            continue
        groups[canonical_key].append(old_key)

    merges: dict[str, list[str]] = {}
    for canonical_key, old_keys in groups.items():
        to_merge = [k for k in old_keys if k != canonical_key]
        if to_merge:
            merges[canonical_key] = to_merge
    return merges


def _topic_for_key(
    members: list[PolicyCandidate], key: str,
) -> str:
    for c in members:
        if c.policy_key == key:
            return c.policy_topic
    return "unknown"


async def execute_key_merge(
    *,
    session: AsyncSession,
    survivor_key: str,
    merged_keys: list[str],
    submission_lane: str = "policy_proposal",
) -> None:
    """Move candidates and endorsements from merged clusters to the survivor."""
    survivor_result = await session.execute(
        select(Cluster).where(
            Cluster.policy_key == survivor_key,
            Cluster.submission_lane == submission_lane,
            Cluster.status == "open",
        )
    )
    survivor = survivor_result.scalar_one_or_none()
    if survivor is None:
        logger.warning("Survivor cluster not found: %s", survivor_key)
        return

    for merged_key in merged_keys:
        affected_candidates_result = await session.execute(
            select(PolicyCandidate).where(PolicyCandidate.policy_key == merged_key)
        )
        affected_candidates = list(affected_candidates_result.scalars().all())
        merged_result = await session.execute(
            select(Cluster).where(
                Cluster.policy_key == merged_key,
                Cluster.submission_lane == submission_lane,
                Cluster.status == "open",
            )
        )
        merged_cluster = merged_result.scalar_one_or_none()
        if merged_cluster is None:
            continue

        new_ids = set(survivor.candidate_ids) | set(merged_cluster.candidate_ids)
        survivor.candidate_ids = list(new_ids)
        survivor.member_count = len(new_ids)

        await session.execute(
            update(PolicyCandidate)
            .where(PolicyCandidate.policy_key == merged_key)
            .values(policy_key=survivor_key, policy_topic=survivor.policy_topic)
        )

        for candidate in affected_candidates:
            await append_evidence(
                session=session,
                event_type="candidate_rekeyed",
                entity_type="candidate",
                entity_id=candidate.id,
                payload={
                    "candidate_id": str(candidate.id),
                    "submission_id": str(candidate.submission_id),
                    "stage": "normalization",
                    "old_policy_key": merged_key,
                    "new_policy_key": survivor_key,
                    "old_policy_topic": candidate.policy_topic,
                    "new_policy_topic": survivor.policy_topic,
                    "old_ballot_readiness": candidate.ballot_readiness,
                    "new_ballot_readiness": candidate.ballot_readiness,
                    "reason_code": "normalization_merge",
                },
            )

        await append_evidence(
            session=session,
            event_type="cluster_merged",
            entity_type="cluster",
            entity_id=survivor.id,
            payload={
                "survivor_key": survivor_key,
                "merged_key": merged_key,
                "merged_cluster_id": str(merged_cluster.id),
                "new_member_count": survivor.member_count,
            },
        )

        await session.delete(merged_cluster)

    survivor.needs_resummarize = True
    await session.flush()
