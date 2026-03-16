from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter

_SYSTEM_PROMPT = (
    "You are a nonpartisan democratic process analyst. "
    "Your job is to help refine civic concerns into the narrowest faithful proposition draft "
    "without changing the underlying intent. Produce a draft whenever the submissions imply "
    "a real proposition, even if important details still need clarification. "
    "Return null only when the submissions are purely exploratory or too underspecified to support "
    "a trustworthy draft. Do not invent a different agenda."
)

_PROMPT_TEMPLATE = """\
Cluster policy key: "{policy_key}"
UI topic: "{policy_topic}"
Current concern summary: "{summary}"

Citizen submissions:
{submissions_block}

Create a refinement draft for this cluster.

Return JSON only:
{{
  "refinement_draft": "One-sentence concrete proposition draft in English, or null if not enough clarity",
  "refinement_draft_fa": "One-sentence concrete proposition draft in plain Farsi, or null if not enough clarity",
  "refinement_confidence": 0.0,
  "requires_clarification": false,
  "notes": "Short explanation in English about what is still missing or why this draft is plausible"
}}

Rules:
- Stay close to the actual submissions.
- Draft the narrowest faithful proposition implied by the submissions.
- If the core direction is identifiable, prefer a draft over null even when some details are still missing.
- Set refinement_draft/refinement_draft_fa to null only when the submissions are purely exploratory, discussion-only, or too underspecified to support a trustworthy proposition.
- Use requires_clarification=true when the submissions do not supply enough detail for a trustworthy draft.
- Confidence reflects whether the draft captures a real plausible proposition implied by the submissions.
- Keep notes short and concrete: say what is missing, or why the draft is still trustworthy.
"""


def _build_submissions_block(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
) -> str:
    lines: list[str] = []
    for candidate_id in cluster.candidate_ids:
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            continue
        lines.append(
            "- "
            f"[readiness={candidate.ballot_readiness}; actor={candidate.actor_scope}; "
            f"mechanism={candidate.action_mechanism}; target={candidate.target_scope}] "
            f"{candidate.title}: {candidate.summary}"
        )
    return "\n".join(lines) if lines else "(no submissions available)"


def _parse_refinement_payload(text: str) -> dict[str, object]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        nl = cleaned.find("\n")
        if nl != -1:
            cleaned = cleaned[nl + 1:]
        last_fence = cleaned.rfind("```")
        if last_fence != -1:
            cleaned = cleaned[:last_fence].rstrip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object")
    return payload


def _cluster_has_refinable_direction(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
) -> bool:
    members = [
        candidates_by_id[candidate_id]
        for candidate_id in cluster.candidate_ids
        if candidate_id in candidates_by_id
    ]
    return any(candidate.ballot_readiness == "needs-refinement" for candidate in members)


async def generate_refinement_drafts(
    *,
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> None:
    for cluster in clusters:
        if not _cluster_has_refinable_direction(cluster, candidates_by_id):
            cluster.refinement_draft = None
            cluster.refinement_draft_fa = None
            cluster.refinement_confidence = 0.0
            cluster.refinement_requires_clarification = True
            cluster.refinement_notes = None
            continue
        submissions_block = _build_submissions_block(cluster, candidates_by_id)
        prompt = _PROMPT_TEMPLATE.format(
            policy_key=cluster.policy_key,
            policy_topic=cluster.policy_topic,
            summary=cluster.summary,
            submissions_block=submissions_block,
        )
        response = await llm_router.complete(
            tier="english_reasoning",
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
        )
        payload = _parse_refinement_payload(response.text)
        cluster.refinement_draft = (
            str(payload.get("refinement_draft")).strip()
            if payload.get("refinement_draft") not in {None, ""}
            else None
        )
        cluster.refinement_draft_fa = (
            str(payload.get("refinement_draft_fa")).strip()
            if payload.get("refinement_draft_fa") not in {None, ""}
            else None
        )
        cluster.refinement_confidence = float(payload.get("refinement_confidence", 0.0))
        cluster.refinement_requires_clarification = bool(payload.get("requires_clarification", False))
        cluster.refinement_notes = str(payload.get("notes", "")).strip() or None
        await append_evidence(
            session=session,
            event_type="refinement_draft_generated",
            entity_type="cluster",
            entity_id=cluster.id,
            payload={
                "cluster_id": str(cluster.id),
                "policy_key": cluster.policy_key,
                "refinement_draft": cluster.refinement_draft,
                "refinement_confidence": cluster.refinement_confidence,
                "requires_clarification": cluster.refinement_requires_clarification,
                "notes": cluster.refinement_notes,
                "model_version": response.model,
            },
        )
    await session.flush()
