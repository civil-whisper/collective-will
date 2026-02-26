"""Phase 3: Generate stance-neutral ballot questions per policy_key cluster.

For each cluster that needs summarization, gathers all member submissions
and asks the LLM to produce a neutral ballot question suitable for the
endorsement step ("Should this topic appear on the ballot?").
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a nonpartisan policy analyst for a democratic deliberation platform. "
    "Your job is to create a neutral ballot question that describes a policy issue "
    "without taking sides, so citizens can decide whether this topic should appear "
    "on the voting ballot."
)

_PROMPT_TEMPLATE = """\
Policy discussion: "{policy_key}"
Topic area: "{policy_topic}"
Number of submissions: {member_count}

Citizen submissions on this issue (summaries):
{submissions_block}

Generate a stance-neutral ballot question that:
1. Describes the policy issue without taking sides
2. Mentions the range of views expressed by citizens
3. Is concise (1-2 sentences in English, 1-2 sentences in Farsi)
4. Makes clear what voters would be deciding about
5. Also provide a short neutral summary of the policy discussion

Return ONLY raw JSON (no markdown):
{{
  "ballot_question": "English ballot question text",
  "ballot_question_fa": "Farsi ballot question text",
  "summary": "Short neutral English summary of the policy discussion"
}}
"""


def _build_submissions_block(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
) -> str:
    lines: list[str] = []
    for cid in cluster.candidate_ids:
        candidate = candidates_by_id.get(cid)
        if candidate is None:
            continue
        lines.append(f"- [{candidate.stance}] {candidate.title}: {candidate.summary}")
    return "\n".join(lines) if lines else "(no submissions available)"


async def generate_ballot_questions(
    *,
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> int:
    """Generate ballot questions for clusters that need (re-)summarization.

    Returns the number of clusters updated.
    """
    updated = 0
    for cluster in clusters:
        if not cluster.needs_resummarize:
            continue

        submissions_block = _build_submissions_block(cluster, candidates_by_id)
        prompt = _PROMPT_TEMPLATE.format(
            policy_key=cluster.policy_key,
            policy_topic=cluster.policy_topic,
            member_count=cluster.member_count,
            submissions_block=submissions_block,
        )

        try:
            completion = await llm_router.complete(
                tier="english_reasoning",
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.1,
            )
            parsed = _parse_ballot_response(completion.text)
        except Exception:
            logger.exception(
                "Ballot question generation failed for cluster %s (%s)",
                cluster.id, cluster.policy_key,
            )
            continue

        cluster.ballot_question = parsed.get("ballot_question", "")
        cluster.ballot_question_fa = parsed.get("ballot_question_fa", "")
        cluster.summary = parsed.get("summary", cluster.summary)
        cluster.last_summarized_count = cluster.member_count
        cluster.needs_resummarize = False

        await append_evidence(
            session=session,
            event_type="ballot_question_generated",
            entity_type="cluster",
            entity_id=cluster.id,
            payload={
                "policy_key": cluster.policy_key,
                "ballot_question": cluster.ballot_question,
                "member_count": cluster.member_count,
                "model_version": completion.model,
            },
        )
        updated += 1

    await session.flush()
    return updated


def _parse_ballot_response(raw: str) -> dict[str, str]:
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        last = text.rfind("```")
        text = text[nl + 1:last].strip()
    if text and text[0] != "{":
        start = text.find("{")
        if start != -1:
            text = text[start:]
    result: dict[str, str] = json.loads(text)
    return result
