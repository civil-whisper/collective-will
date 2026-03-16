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
    "You are a nonpartisan democratic process analyst. "
    "Your job is to write plain-language, impartial civic wording that resembles "
    "a real democratic process. Preserve the difference between a broad concern "
    "that needs more refinement and a concrete proposition that voters could actually decide."
)

_PROMPT_TEMPLATE = """\
Policy discussion: "{policy_key}"
Number of submissions: {member_count}

Citizen submissions on this issue:
{submissions_block}

Generate two pieces of neutral wording:
1. ballot_question:
   - If the issue is concrete and ballot-ready, write neutral proposition language
     describing what voters would actually be deciding.
   - If the issue is still broad or underspecified, write agenda-setting language
     describing whether this concern should move forward for further public refinement.
2. summary:
   - Write a short neutral summary suitable for a concerns/discussion list.

IMPORTANT formatting rules for the Farsi version (ballot_question_fa):
- Write as a STATEMENT, not a question. Do NOT start with «آیا» or end with «؟».
- Use casual, plain Farsi suitable for people in their early 20s — direct and friendly, not formal or bureaucratic.
- Plain-language civic style is more important than rhetoric.

Ballot-language requirements:
- Use concise, impartial language.
- Avoid "one citizen raised a concern" narration.
- Make clear whether the item is a concrete proposition or still a broad concern under discussion.
- Do not invent an option set or political spectrum in this step.

Return ONLY raw JSON (no markdown):
{{
  "ballot_question": "English policy description (statement format)",
  "ballot_question_fa": "Farsi policy description (statement, casual tone, no آیا, no ؟)",
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
        lines.append(
            "- "
            f"[{candidate.stance}; actor={candidate.actor_scope}; mechanism={candidate.action_mechanism}; "
            f"target={candidate.target_scope}; readiness={candidate.ballot_readiness}] "
            f"{candidate.title}: {candidate.summary}"
        )
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
        except Exception as exc:
            logger.exception(
                "Ballot question generation failed for cluster %s (%s)",
                cluster.id, cluster.policy_key,
            )
            await append_evidence(
                session=session,
                event_type="ballot_generation_failed",
                entity_type="cluster",
                entity_id=cluster.id,
                payload={
                    "cluster_id": str(cluster.id),
                    "policy_key": cluster.policy_key,
                    "error_type": type(exc).__name__,
                },
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
