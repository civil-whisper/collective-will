"""Phase 2: LLM-based policy key normalization within each policy_topic.

Periodically reviews all policy_keys under each topic and merges
near-duplicates that represent the same ballot-level discussion.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter

logger = logging.getLogger(__name__)

_NORMALIZATION_SYSTEM_PROMPT = (
    "You are a policy analyst for a democratic deliberation platform. "
    "Your job is to review policy discussion keys within a topic and identify "
    "near-duplicates that should be merged because they represent the same "
    "ballot-level discussion, just named differently."
)

_NORMALIZATION_PROMPT_TEMPLATE = """\
Topic: "{topic}"

Current policy keys and their descriptions:
{keys_block}

Should any of these be MERGED because they represent the same ballot-level \
discussion (just named differently)?

Rules:
- Merge ONLY if they are truly the same specific issue (just named differently).
- Do NOT merge if they are different aspects of the same broad topic.
- The survivor key should be the most descriptive and commonly used name.

Reply with ONLY a raw JSON object (no markdown):
{{"merges": [{{"keys": ["key-a", "key-b"], "survivor": "key-a"}}]}}
Or if no merges needed:
{{"merges": []}}
"""


@dataclass(slots=True)
class KeyMerge:
    topic: str
    merged_keys: list[str]
    survivor_key: str


def _build_keys_block(
    keys: list[tuple[str, int, str]],
) -> str:
    lines: list[str] = []
    for i, (key, count, desc) in enumerate(keys, 1):
        lines.append(f"  {i}. \"{key}\" ({count} submissions)")
        lines.append(f"     Typical: {desc}")
    return "\n".join(lines)


async def normalize_policy_keys(
    *,
    session: AsyncSession,
    llm_router: LLMRouter,
) -> list[KeyMerge]:
    """For each topic with multiple keys, ask the LLM to identify merges."""
    result = await session.execute(
        select(
            Cluster.policy_topic,
            Cluster.policy_key,
            Cluster.member_count,
            Cluster.summary,
        )
        .where(Cluster.policy_key != "unassigned")
        .order_by(Cluster.policy_topic, Cluster.member_count.desc())
    )
    rows = result.all()

    topics: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for topic, key, count, summary in rows:
        short = (summary or "")[:150].replace("\n", " ")
        topics[topic].append((key, count, short))

    all_merges: list[KeyMerge] = []
    for topic, keys in topics.items():
        if len(keys) < 2:
            continue

        keys_block = _build_keys_block(keys)
        prompt = _NORMALIZATION_PROMPT_TEMPLATE.format(
            topic=topic, keys_block=keys_block,
        )

        try:
            completion = await llm_router.complete(
                tier="english_reasoning",
                prompt=prompt,
                system_prompt=_NORMALIZATION_SYSTEM_PROMPT,
                temperature=0.0,
            )
            parsed = _parse_merge_response(completion.text)
        except Exception:
            logger.exception("Key normalization failed for topic %s", topic)
            continue

        for merge_spec in parsed:
            merge_keys = merge_spec.get("keys", [])
            survivor = merge_spec.get("survivor", "")
            if len(merge_keys) < 2 or not survivor or survivor not in merge_keys:
                continue

            to_merge = [k for k in merge_keys if k != survivor]
            await execute_key_merge(
                session=session, survivor_key=survivor, merged_keys=to_merge,
            )
            all_merges.append(KeyMerge(
                topic=topic, merged_keys=to_merge, survivor_key=survivor,
            ))

    return all_merges


def _parse_merge_response(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        last = text.rfind("```")
        text = text[nl + 1:last].strip()
    data = json.loads(text)
    return list(data.get("merges", []))


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
