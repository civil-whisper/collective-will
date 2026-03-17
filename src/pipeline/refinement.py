from __future__ import annotations

import json
import re
from collections.abc import Mapping
from collections import Counter
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
    "a trustworthy draft. Do not invent a different agenda, actor, jurisdiction, or target."
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
- Keep the draft in the same language split as requested: English in refinement_draft, plain Farsi in refinement_draft_fa.
- Do not introduce a new actor, institution, city, or jurisdiction unless it is explicit in the submissions.
- If the actor is unclear, keep the draft actor-neutral instead of inventing who should act.
- Do not turn a broad worry, conditional statement, or open-ended concern into a more specific or more forceful proposition than the submissions support.
- If the core direction is identifiable, prefer a draft over null even when some details are still missing.
- Set refinement_draft/refinement_draft_fa to null only when the submissions are purely exploratory, discussion-only, or too underspecified to support a trustworthy proposition.
- Use requires_clarification=true when the submissions do not supply enough detail for a trustworthy draft.
- Confidence reflects whether the draft captures a real plausible proposition implied by the submissions.
- Keep notes short and concrete: say what is missing, or why the draft is still trustworthy.
"""

_LOCAL_ACTOR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bthe city should\b", flags=re.IGNORECASE), "Draft introduced a city-level actor not present in the source submissions."),
    (re.compile(r"\bmunicipalit(?:y|ies)\b", flags=re.IGNORECASE), "Draft introduced a municipal actor not present in the source submissions."),
    (re.compile(r"\bmayor\b", flags=re.IGNORECASE), "Draft introduced a mayoral actor not present in the source submissions."),
    (re.compile(r"\bcity council\b", flags=re.IGNORECASE), "Draft introduced a local council actor not present in the source submissions."),
)
_UNANCHORED_TARGET_PHRASES = (
    "against iran",
    "against the iranian regime",
    "against iran's government",
    "against the government of iran",
)


def _build_submissions_block(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
) -> str:
    lines: list[str] = []
    for candidate_id in cluster.candidate_ids:
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            continue
        ambiguity_flags = getattr(candidate, "ambiguity_flags", None) or []
        flags_text = ", ".join(str(flag) for flag in ambiguity_flags) if ambiguity_flags else "none"
        readiness_reason = getattr(candidate, "ballot_readiness_reason", None) or "none"
        lines.append(
            "- "
            f"[stance={candidate.stance}; readiness={candidate.ballot_readiness}; "
            f"actor={candidate.actor_scope}; mechanism={candidate.action_mechanism}; "
            f"target={candidate.target_scope}; reason={readiness_reason}; flags={flags_text}] "
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


def _cluster_members(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
) -> list[PolicyCandidate]:
    return [
        candidates_by_id[candidate_id]
        for candidate_id in cluster.candidate_ids
        if candidate_id in candidates_by_id
    ]


def _dominant_member_value(members: list[PolicyCandidate], attr: str) -> str | None:
    counts = Counter(
        str(getattr(member, attr, "")).strip()
        for member in members
        if str(getattr(member, attr, "")).strip() not in {"", "unclear", "other", "neutral"}
    )
    if not counts:
        return None
    value, count = counts.most_common(1)[0]
    if count * 2 < len(members):
        return None
    return value


def _build_source_corpus(cluster: Cluster, members: list[PolicyCandidate]) -> str:
    parts = [cluster.policy_key, cluster.policy_topic]
    for member in members:
        parts.extend([
            str(getattr(member, "title", "")),
            str(getattr(member, "summary", "")),
            str(getattr(member, "ballot_readiness_reason", "")),
            " ".join(str(flag) for flag in (getattr(member, "ambiguity_flags", None) or [])),
            " ".join(str(entity) for entity in (getattr(member, "entities", None) or [])),
        ])
    return " ".join(part for part in parts if part).lower()


def _draft_direction(text: str) -> str | None:
    lowered = text.lower().strip()
    if lowered.startswith(("oppose ", "reject ", "ban ", "stop ", "prevent ")):
        return "oppose"
    if lowered.startswith(("support ", "adopt ", "approve ", "allow ", "apply ", "require ")):
        return "support"
    return None


def _tone_soften_refinement_output(
    *,
    draft: str | None,
    draft_fa: str | None,
    requires_clarification: bool,
) -> tuple[str | None, str | None]:
    if draft is None:
        return draft, draft_fa

    softened_draft = draft
    softened_fa = draft_fa
    english_question_rewrites = (
        (r"^Should (.+?) be supported( .+)?\?$", r"\1 should be supported\2."),
        (r"^Should (.+?) be opposed( .+)?\?$", r"\1 should be opposed\2."),
        (r"^Should (.+?) be used( .+)?\?$", r"\1 should be used\2."),
        (r"^Should (.+?) be applied( .+)?\?$", r"\1 should be applied\2."),
        (r"^Should (.+)\?$", r"\1 should be considered."),
    )
    for pattern, replacement in english_question_rewrites:
        updated = re.sub(pattern, replacement, softened_draft)
        if updated != softened_draft:
            softened_draft = updated[0].upper() + updated[1:] if updated else updated
            break

    if softened_fa is not None:
        farsi_question_rewrites = (
            (r"^آیا باید از (.+) حمایت شود؟$", r"از \1 حمایت شود."),
            (r"^آیا باید با (.+) مخالفت شود؟$", r"با \1 مخالفت شود."),
            (r"^آیا باید از (.+) استفاده شود؟$", r"از \1 استفاده شود."),
            (r"^آیا باید (.+?) اعمال شود(.*)؟$", r"\1 اعمال شود\2."),
        )
        for pattern, replacement in farsi_question_rewrites:
            updated_fa = re.sub(pattern, replacement, softened_fa)
            if updated_fa != softened_fa:
                softened_fa = updated_fa
                break

    if not requires_clarification:
        return softened_draft, softened_fa

    english_rewrites = (
        (r"^Support (.+)\.$", r"\1 should be supported."),
        (r"^Oppose (.+)\.$", r"\1 should be opposed."),
        (r"^Use (.+)\.$", r"\1 should be used."),
        (r"^Apply (.+)\.$", r"\1 should be applied."),
        (r"^Support for (.+)\.$", r"Support for \1 should be maintained."),
    )
    for pattern, replacement in english_rewrites:
        updated = re.sub(pattern, replacement, softened_draft)
        if updated != softened_draft:
            softened_draft = updated[0].upper() + updated[1:] if updated else updated
            break

    if softened_fa is not None:
        farsi_rewrites = (
            (r"^از (.+) حمایت کنید\.$", r"از \1 حمایت شود."),
            (r"^از (.+) حمایت کنید$", r"از \1 حمایت شود."),
            (r"^با (.+) مخالفیم\.$", r"با \1 مخالفت شود."),
            (r"^از (.+) استفاده شود\.$", r"از \1 استفاده شود."),
        )
        for pattern, replacement in farsi_rewrites:
            updated_fa = re.sub(pattern, replacement, softened_fa)
            if updated_fa != softened_fa:
                softened_fa = updated_fa
                break

    return softened_draft, softened_fa


def _sanitize_refinement_output(
    *,
    cluster: Cluster,
    members: list[PolicyCandidate],
    payload: dict[str, object],
) -> tuple[str | None, str | None, float, bool, str | None, list[str]]:
    draft = str(payload.get("refinement_draft")).strip() if payload.get("refinement_draft") not in {None, ""} else None
    draft_fa = str(payload.get("refinement_draft_fa")).strip() if payload.get("refinement_draft_fa") not in {None, ""} else None
    confidence = float(payload.get("refinement_confidence", 0.0))
    requires_clarification = bool(payload.get("requires_clarification", False))
    notes = str(payload.get("notes", "")).strip() or None
    validation_flags: list[str] = []

    if draft is None:
        if draft_fa is not None:
            validation_flags.append("Draft returned Farsi text without an English draft.")
        return None, None, 0.0 if draft_fa is not None else confidence, True if draft_fa is not None else requires_clarification, notes, validation_flags

    draft_lower = draft.lower()
    source_corpus = _build_source_corpus(cluster, members)
    dominant_target = _dominant_member_value(members, "target_scope")
    dominant_stance = _dominant_member_value(members, "stance")

    for pattern, message in _LOCAL_ACTOR_PATTERNS:
        if pattern.search(draft) and not pattern.search(source_corpus):
            validation_flags.append(message)

    if dominant_target is None:
        for phrase in _UNANCHORED_TARGET_PHRASES:
            if phrase in draft_lower and phrase not in source_corpus:
                validation_flags.append("Draft introduced a specific target that is not anchored in the source submissions.")
                break

    draft_direction = _draft_direction(draft)
    if dominant_stance in {"support", "oppose"} and draft_direction is not None and draft_direction != dominant_stance:
        validation_flags.append("Draft changed the overall direction of the cluster.")

    if validation_flags:
        merged_notes = "; ".join(validation_flags)
        if notes:
            merged_notes = f"{notes} {merged_notes}"
        return None, None, 0.0, True, merged_notes, validation_flags
    softened_draft, softened_draft_fa = _tone_soften_refinement_output(
        draft=draft,
        draft_fa=draft_fa,
        requires_clarification=requires_clarification,
    )
    return softened_draft, softened_draft_fa, confidence, requires_clarification, notes, validation_flags


async def generate_refinement_drafts(
    *,
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> None:
    for cluster in clusters:
        members = _cluster_members(cluster, candidates_by_id)
        if not any(candidate.ballot_readiness == "needs-refinement" for candidate in members):
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
        (
            cluster.refinement_draft,
            cluster.refinement_draft_fa,
            cluster.refinement_confidence,
            cluster.refinement_requires_clarification,
            cluster.refinement_notes,
            validation_flags,
        ) = _sanitize_refinement_output(
            cluster=cluster,
            members=members,
            payload=payload,
        )
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
                "validation_flags": validation_flags,
                "model_version": response.model,
            },
        )
    await session.flush()
