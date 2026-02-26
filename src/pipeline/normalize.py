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
- The canonical key should be stance-neutral, descriptive, and use \
lowercase-with-hyphens.
- You may create a new key name if no existing key captures the group well.
- Keys that should stay separate can map to themselves.

Reply with ONLY a raw JSON object (no markdown):
{{"key_mapping": {{"old-key-1": "canonical-key", "old-key-2": "canonical-key", \
"old-key-3": "old-key-3"}}}}
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
            f'  {i}. [key: "{entry["key"]}", topic: "{entry["topic"]}", '
            f'{entry["count"]} submissions]'
        )
        lines.append(f"     {entry['summary']}")
    return "\n".join(lines)


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
        distinct_keys = {c.policy_key for c in members}
        if len(distinct_keys) < 2:
            continue

        entries = _build_entries_for_cluster(members)
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
        except Exception:
            logger.exception(
                "Normalization LLM call failed for embedding cluster with keys %s",
                distinct_keys,
            )
            continue

        merges = _extract_merges_from_mapping(key_mapping, distinct_keys)
        for survivor_key, merged_keys in merges.items():
            await execute_key_merge(
                session=session,
                survivor_key=survivor_key,
                merged_keys=merged_keys,
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
        })
    return entries


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
) -> None:
    """Move candidates and endorsements from merged clusters to the survivor."""
    survivor_result = await session.execute(
        select(Cluster).where(Cluster.policy_key == survivor_key)
    )
    survivor = survivor_result.scalar_one_or_none()
    if survivor is None:
        logger.warning("Survivor cluster not found: %s", survivor_key)
        return

    for merged_key in merged_keys:
        merged_result = await session.execute(
            select(Cluster).where(Cluster.policy_key == merged_key)
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
            .values(policy_key=survivor_key)
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
