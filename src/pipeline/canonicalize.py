from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.submission import PolicyCandidateCreate
from src.pipeline.llm import LLMRouter
from src.pipeline.privacy import prepare_batch_for_llm, re_link_results, validate_no_metadata

_STANCES = "support, oppose, neutral, unclear"
_DEFAULT_ACTOR_SCOPE = "unclear"
_DEFAULT_ACTION_MECHANISM = "unclear"
_DEFAULT_TARGET_SCOPE = "unclear"
_DEFAULT_BALLOT_READINESS = "discussion-only"
_ALLOWED_ACTOR_SCOPES = {
    "domestic-citizens",
    "foreign-state",
    "international-organization",
    "civil-society",
    "public-governance",
    "unclear",
}
_ALLOWED_ACTION_MECHANISMS = {
    "labor-strike",
    "economic-sanctions",
    "economic-pressure",
    "military-action",
    "diplomatic-pressure",
    "civil-society-support",
    "governance-design",
    "discussion-only",
    "unclear",
}
_ALLOWED_TARGET_SCOPES = {
    "iranian-regime",
    "iranian-economy",
    "public-governance",
    "civil-rights",
    "unclear",
}
_ALLOWED_BALLOT_READINESS = {"ballot-ready", "needs-refinement", "discussion-only"}

def _sanitize_policy_slug(value: str) -> str:
    """Normalize a policy_topic or policy_key to lowercase-with-hyphens."""
    slug = value.strip().lower()
    slug = slug.replace("_", "-").replace(" ", "-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "unassigned"


async def load_existing_policy_context(session: AsyncSession) -> str:
    """Load open policy keys from clusters, formatted for the LLM prompt."""
    from src.models.cluster import Cluster

    result = await session.execute(
        select(
            Cluster.policy_key,
            Cluster.member_count,
            Cluster.summary,
        )
        .where(Cluster.status == "open")
        .order_by(Cluster.member_count.desc(), Cluster.policy_key.asc())
    )
    rows = result.all()
    if not rows:
        return ""

    entries: list[tuple[str, int, str]] = []
    for key, count, summary in rows:
        if key == "unassigned":
            continue
        clean_summary = (summary or "").replace("\n", " ")
        entries.append((key, count, clean_summary))

    if not entries:
        return ""

    lines: list[str] = []
    for key, count, desc in entries:
        lines.append(f'  - "{key}" ({count} submissions) — {desc}')
    return "\n".join(lines)


_SYSTEM_PROMPT = (
    "You are processing civic submissions for a democratic deliberation platform. "
    "Citizens submit policy ideas, concerns, or questions in any language (often Farsi "
    "or English). Your job is to determine whether the input relates to a civic or "
    "policy topic and, if so, convert it into canonical structured form. All canonical "
    "output (title, summary, entities, policy_topic, policy_key, actor_scope, "
    "action_mechanism, target_scope, ballot_readiness, ballot_readiness_reason) "
    "must be in English "
    "regardless of the input language."
)

_JSON_REPAIR_SYSTEM_PROMPT = (
    "You repair malformed JSON. "
    "Return valid JSON only. Do not add commentary, markdown, or explanations. "
    "Preserve the original meaning and field names."
)


def _sanitize_semantic_value(value: str, *, allowed: set[str], default: str) -> str:
    slug = _sanitize_policy_slug(value)
    return slug if slug in allowed else default


def _prompt_for_item(item: dict[str, Any], policy_context: str = "") -> str:
    context_block = ""
    if policy_context:
        context_block = (
            "\nEXISTING OPEN POLICY KEYS (reuse one only if actor, mechanism, and target materially match):\n"
            f"{policy_context}\n"
            "ASSIGNMENT RULES:\n"
            "- Reuse an EXISTING policy_key only when the actor, mechanism, and target "
            "all materially match.\n"
            "- Do NOT reuse a key based only on a shared political goal or shared mention "
            "of regime change.\n"
            "- Domestic labor strikes, foreign sanctions, diplomatic pressure, and "
            "military intervention must remain separate policy_keys unless they are "
            "truly the same proposition.\n"
            "- If actor or mechanism differs, create a NEW policy_key.\n\n"
        )
    return (
        "Evaluate and canonicalize this civic submission into structured JSON.\n\n"
        "LANGUAGE RULES:\n"
        "- Detect the input language automatically.\n"
        "- title, summary, entities, policy_topic, policy_key, actor_scope, "
        "action_mechanism, target_scope, ballot_readiness, and ballot_readiness_reason "
        "MUST always be in "
        "English (translate if the input is in another language).\n"
        "- rejection_reason MUST be in the SAME LANGUAGE as the input "
        "(so the user can understand it).\n\n"
        "VALIDITY: A valid submission is anything that relates to governance, laws, "
        "rights, economy, foreign policy, or public affairs. This includes:\n"
        "- Direct positions, suggestions, or demands ('We should do X')\n"
        "- Questions or concerns about a policy topic ('What should happen with X?')\n"
        "- Expressions of worry or interest in a public issue ('I'm concerned about X')\n"
        "All of these are valid because they identify a policy topic citizens care about. "
        "Invalid inputs include: random text, greetings, purely personal matters unrelated "
        "to public policy, spam, platform questions ('how does this bot work?'), "
        "or completely off-topic content.\n\n"
        + context_block
        + "Required JSON fields:\n"
        "  is_valid_policy (bool): true if valid civic/policy proposal, false otherwise,\n"
        "  rejection_reason (str or null): if invalid, explain in the INPUT language,\n"
        "  title (str, ENGLISH),\n"
        "  summary (str, ENGLISH — concise but accurate description of the submission),\n"
        f"  stance (one of: {_STANCES}),\n"
        "  policy_topic (str, ENGLISH): optional browsing label for the UI, lowercase-with-hyphens, "
        "1-4 words. This is display metadata, not the main semantic identity.\n"
        "    Examples: \"economic-resistance\", \"dress-code-policy\", \"healthcare-access\"\n"
        "  policy_key (str, ENGLISH): specific ballot-level discussion, "
        "lowercase-with-hyphens, 2-6 words. MUST be stance-neutral (no support/oppose "
        "language). Specific enough that 2-4 ballot options can cover the full discussion.\n"
        "    GOOD: \"political-internet-censorship\", \"mandatory-hijab-policy\", "
        "\"death-penalty\"\n"
        "    BAD: \"abolish-mandatory-hijab\" (has a stance), \"women-rights\" (too broad)\n"
        "  actor_scope (str, ENGLISH): who would primarily act or apply pressure. "
        "Use lowercase-with-hyphens. Prefer one of: domestic-citizens, foreign-state, "
        "international-organization, civil-society, unclear.\n"
        "  action_mechanism (str, ENGLISH): how the action works. Prefer one of: "
        "labor-strike, economic-sanctions, economic-pressure, military-action, "
        "diplomatic-pressure, civil-society-support, governance-design, discussion-only, unclear.\n"
        "  target_scope (str, ENGLISH): what the action primarily targets. Prefer one of: "
        "iranian-regime, iranian-economy, public-governance, civil-rights, unclear.\n"
        "  ballot_readiness (str, ENGLISH): one of ballot-ready, needs-refinement, discussion-only.\n"
        "  ballot_readiness_reason (str, ENGLISH): short reason explaining why the issue is "
        "or is not specific enough for a ballot proposition.\n"
        "  entities (list of strings, ENGLISH), confidence (float 0-1), "
        "ambiguity_flags (list of strings).\n\n"
        "Examples of distinctions you MUST preserve:\n"
        "- 'Workers should strike to weaken the regime economically' => actor_scope domestic-citizens, "
        "action_mechanism labor-strike. Do NOT map this to foreign sanctions or military intervention.\n"
        "- 'The US should sanction Iran harder' => actor_scope foreign-state, action_mechanism economic-sanctions.\n"
        "- 'What political system should come after regime change?' => action_mechanism governance-design, "
        "not sanctions, strikes, or intervention.\n\n"
        "If is_valid_policy is false, set policy_topic and policy_key to \"unassigned\" "
        "and set actor_scope/action_mechanism/target_scope to \"unclear\", "
        "ballot_readiness to \"discussion-only\", and confidence to 0.\n"
        "Return ONLY the raw JSON object, no markdown wrapping.\n\n"
        f"Input: {json.dumps(item, ensure_ascii=False)}"
    )


@dataclass(slots=True)
class CanonicalizationRejection:
    reason: str
    model_version: str
    prompt_version: str


def _prompt_version(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _parse_candidate_payload(payload: str) -> tuple[dict[str, Any], str | None]:
    """Parse LLM output JSON. Returns (data, repair_method) where repair_method
    is None for clean parse or ``"regex"`` when local regex repair was applied."""
    text = payload.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
        if text.endswith("```"):
            text = text[:-3].rstrip()
    if text and text[0] not in ("{", "["):
        start = text.find("{")
        if start != -1:
            text = text[start:]
            depth, end = 0, 0
            for i, ch in enumerate(text):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end:
                text = text[:end]
    repair_method: str | None = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        repaired = re.sub(
            r'(?P<prefix>[{,]\s*)"(?P<key>[^"]+)"\s*,(?=\s*(?:true|false|null|-?\d|"|\{|\[))',
            r'\g<prefix>"\g<key>":',
            text,
        )
        repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
        data = json.loads(repaired)
        repair_method = "regex"
    if isinstance(data, list):
        return cast(dict[str, Any], data[0]), repair_method
    return cast(dict[str, Any], data), repair_method


async def _parse_candidate_payload_with_repair(
    *,
    payload: str,
    llm_router: LLMRouter,
) -> tuple[dict[str, Any], str | None]:
    """Parse with optional LLM repair fallback.
    Returns (data, repair_method): None, ``"regex"``, or ``"llm"``."""
    try:
        return _parse_candidate_payload(payload)
    except json.JSONDecodeError:
        repair_prompt = (
            "Repair this malformed canonicalization JSON into strict valid JSON.\n"
            "Return only the repaired JSON object.\n\n"
            f"{payload}"
        )
        repaired = await llm_router.complete(
            tier="canonicalization",
            prompt=repair_prompt,
            system_prompt=_JSON_REPAIR_SYSTEM_PROMPT,
        )
        data, _ = _parse_candidate_payload(repaired.text)
        return data, "llm"


def _build_candidate_create(
    output: dict[str, Any],
    submission_id: UUID,
) -> PolicyCandidateCreate:
    """Build a PolicyCandidateCreate from parsed LLM output."""
    confidence = float(output.get("confidence", 0.0))
    flags = list(output.get("ambiguity_flags", []))
    if confidence < 0.7 and "low_confidence" not in flags:
        flags.append("low_confidence")

    stance_raw = str(output.get("stance", "unclear")).lower().strip()
    stance_map = {"supportive": "support", "opposing": "oppose", "opposed": "oppose"}
    stance = stance_map.get(stance_raw, stance_raw)
    if stance not in {"support", "oppose", "neutral", "unclear"}:
        stance = "unclear"

    entities_raw = output.get("entities", [])
    entities = [
        str(e) if isinstance(e, str)
        else str(e.get("text", e)) if isinstance(e, dict)
        else str(e)
        for e in entities_raw
    ]

    policy_topic = _sanitize_policy_slug(str(output.get("policy_topic", "unassigned")))
    policy_key = _sanitize_policy_slug(str(output.get("policy_key", "unassigned")))
    actor_scope = _sanitize_semantic_value(
        str(output.get("actor_scope", _DEFAULT_ACTOR_SCOPE)),
        allowed=_ALLOWED_ACTOR_SCOPES,
        default=_DEFAULT_ACTOR_SCOPE,
    )
    action_mechanism = _sanitize_semantic_value(
        str(output.get("action_mechanism", _DEFAULT_ACTION_MECHANISM)),
        allowed=_ALLOWED_ACTION_MECHANISMS,
        default=_DEFAULT_ACTION_MECHANISM,
    )
    target_scope = _sanitize_semantic_value(
        str(output.get("target_scope", _DEFAULT_TARGET_SCOPE)),
        allowed=_ALLOWED_TARGET_SCOPES,
        default=_DEFAULT_TARGET_SCOPE,
    )
    ballot_readiness = _sanitize_semantic_value(
        str(output.get("ballot_readiness", _DEFAULT_BALLOT_READINESS)),
        allowed=_ALLOWED_BALLOT_READINESS,
        default=_DEFAULT_BALLOT_READINESS,
    )
    ballot_readiness_reason = str(output.get("ballot_readiness_reason", "")).strip() or None

    return PolicyCandidateCreate(
        submission_id=submission_id,
        title=str(output.get("title", "Untitled policy candidate")),
        summary=str(output.get("summary", "")),
        stance=stance,
        policy_topic=policy_topic,
        policy_key=policy_key,
        actor_scope=actor_scope,
        action_mechanism=action_mechanism,
        target_scope=target_scope,
        ballot_readiness=ballot_readiness,
        ballot_readiness_reason=ballot_readiness_reason,
        entities=entities,
        confidence=confidence,
        ambiguity_flags=flags,
        model_version=str(output["model_version"]),
        prompt_version=str(output["prompt_version"]),
        embedding=None,
    )


async def canonicalize_single(
    *,
    session: AsyncSession,
    submission_id: UUID,
    raw_text: str,
    language: str,
    llm_router: LLMRouter,
    policy_context: str = "",
) -> PolicyCandidateCreate | CanonicalizationRejection:
    """Canonicalize one submission inline. Returns candidate data or rejection."""
    if not policy_context:
        policy_context = await load_existing_policy_context(session)

    sanitized, _ = prepare_batch_for_llm([{"raw_text": raw_text, "language": language}])
    if not validate_no_metadata(sanitized):
        raise ValueError("Sanitized payload still contains metadata")

    item = sanitized[0]
    prompt = _prompt_for_item(item, policy_context=policy_context)
    completion = await llm_router.complete(
        tier="canonicalization", prompt=prompt, system_prompt=_SYSTEM_PROMPT,
    )
    parsed, repair_method = await _parse_candidate_payload_with_repair(
        payload=completion.text,
        llm_router=llm_router,
    )
    parsed["model_version"] = completion.model
    parsed["prompt_version"] = _prompt_version(prompt)

    if repair_method is not None:
        await append_evidence(
            session=session,
            event_type="candidate_parse_repaired",
            entity_type="submission",
            entity_id=submission_id,
            payload={
                "submission_id": str(submission_id),
                "repair_method": repair_method,
                "model_version": completion.model,
            },
        )

    if not parsed.get("is_valid_policy", True):
        reason = str(parsed.get("rejection_reason") or "Submission is not a valid policy proposal.")
        await append_evidence(
            session=session,
            event_type="submission_rejected_not_policy",
            entity_type="submission",
            entity_id=submission_id,
            payload={
                "submission_id": str(submission_id),
                "rejection_reason": reason,
                "model_version": parsed["model_version"],
                "prompt_version": parsed["prompt_version"],
            },
        )
        return CanonicalizationRejection(
            reason=reason,
            model_version=str(parsed["model_version"]),
            prompt_version=str(parsed["prompt_version"]),
        )

    candidate = _build_candidate_create(parsed, submission_id)
    await append_evidence(
        session=session,
        event_type="candidate_created",
        entity_type="submission",
        entity_id=submission_id,
        payload={
            "submission_id": str(submission_id),
            "title": candidate.title,
            "summary": candidate.summary,
            "stance": candidate.stance,
            "policy_topic": candidate.policy_topic,
            "policy_key": candidate.policy_key,
            "actor_scope": candidate.actor_scope,
            "action_mechanism": candidate.action_mechanism,
            "target_scope": candidate.target_scope,
            "ballot_readiness": candidate.ballot_readiness,
            "ballot_readiness_reason": candidate.ballot_readiness_reason,
            "confidence": candidate.confidence,
            "model_version": candidate.model_version,
            "prompt_version": candidate.prompt_version,
        },
    )
    return candidate


async def canonicalize_batch(
    *,
    session: AsyncSession,
    submissions: list[dict[str, Any]],
    llm_router: LLMRouter,
    policy_context: str = "",
) -> list[PolicyCandidateCreate]:
    if not policy_context:
        policy_context = await load_existing_policy_context(session)

    sanitized, index_map = prepare_batch_for_llm(submissions)
    if not validate_no_metadata(sanitized):
        raise ValueError("Sanitized payload still contains metadata")

    llm_outputs: list[dict[str, Any]] = []
    for idx_s, item in enumerate(sanitized):
        prompt = _prompt_for_item(item, policy_context=policy_context)
        completion = await llm_router.complete(
            tier="canonicalization", prompt=prompt, system_prompt=_SYSTEM_PROMPT,
        )
        parsed, repair_method = await _parse_candidate_payload_with_repair(
            payload=completion.text,
            llm_router=llm_router,
        )
        parsed["model_version"] = completion.model
        parsed["prompt_version"] = _prompt_version(prompt)
        llm_outputs.append(parsed)

        if repair_method is not None:
            sub_id = submissions[idx_s]["id"]
            await append_evidence(
                session=session,
                event_type="candidate_parse_repaired",
                entity_type="submission",
                entity_id=sub_id,
                payload={
                    "submission_id": str(sub_id),
                    "repair_method": repair_method,
                    "model_version": completion.model,
                },
            )

    ordered = re_link_results(llm_outputs, index_map)
    candidates: list[PolicyCandidateCreate] = []
    for idx, output in enumerate(ordered):
        if not output.get("is_valid_policy", True):
            reason = str(output.get("rejection_reason") or "Submission is not a valid policy proposal.")
            await append_evidence(
                session=session,
                event_type="submission_rejected_not_policy",
                entity_type="submission",
                entity_id=submissions[idx]["id"],
                payload={
                    "submission_id": str(submissions[idx]["id"]),
                    "rejection_reason": reason,
                    "model_version": str(output.get("model_version", "")),
                    "prompt_version": str(output.get("prompt_version", "")),
                },
            )
            continue

        candidate = _build_candidate_create(output, submissions[idx]["id"])
        candidates.append(candidate)
        await append_evidence(
            session=session,
            event_type="candidate_created",
            entity_type="submission",
            entity_id=submissions[idx]["id"],
            payload={
                "submission_id": str(submissions[idx]["id"]),
                "title": candidate.title,
                "summary": candidate.summary,
                "stance": candidate.stance,
                "policy_topic": candidate.policy_topic,
                "policy_key": candidate.policy_key,
                "actor_scope": candidate.actor_scope,
                "action_mechanism": candidate.action_mechanism,
                "target_scope": candidate.target_scope,
                "ballot_readiness": candidate.ballot_readiness,
                "ballot_readiness_reason": candidate.ballot_readiness_reason,
                "confidence": candidate.confidence,
                "model_version": candidate.model_version,
                "prompt_version": candidate.prompt_version,
            },
        )
    return candidates
