from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
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
    "other",
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
    "other",
    "unclear",
}
_ALLOWED_TARGET_SCOPES = {
    "iranian-regime",
    "iranian-economy",
    "public-governance",
    "civil-rights",
    "other",
    "unclear",
}
_ALLOWED_BALLOT_READINESS = {"ballot-ready", "needs-refinement", "discussion-only"}

def _sanitize_policy_slug(value: str) -> str:
    """Normalize a policy_topic or policy_key to lowercase-with-hyphens."""
    slug = value.strip().lower()
    slug = slug.replace("_", "-").replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "unassigned"


async def load_existing_policy_context(session: AsyncSession) -> str:
    """Load open policy keys from clusters, formatted for the LLM prompt."""
    from src.models.cluster import Cluster
    settings = get_settings()

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
    summary_chars = max(40, settings.canonicalization_context_summary_chars)
    max_entries = max(1, settings.canonicalization_context_max_entries)
    for key, count, desc in entries[:max_entries]:
        short_desc = desc[:summary_chars].rstrip()
        if len(desc) > summary_chars:
            short_desc += "..."
        lines.append(f'  - "{key}" ({count}) — {short_desc}')
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


_CANONICALIZATION_INSTRUCTIONS = (
    "Canonicalize this civic submission into JSON.\n\n"
    "Rules:\n"
    "- Detect input language.\n"
    "- Canonical fields (title, summary, entities, policy_topic, policy_key, actor_scope, "
    "action_mechanism, target_scope, ballot_readiness, ballot_readiness_reason) must be in English.\n"
    "- rejection_reason is the only user-facing field that must stay in the input language.\n"
    "- If the input is English, rejection_reason must be English, not Farsi.\n"
    "- If the input is Farsi, rejection_reason must be Farsi, not English.\n"
    "- Valid submissions include civic or policy positions, questions, concerns, and expressions of interest "
    "about governance, rights, economy, foreign policy, or public affairs.\n"
    "- Invalid submissions include greetings, spam, personal/off-topic text, and platform/how-to questions.\n"
    "- discussion-only = broad exploration with no implied proposition.\n"
    "- needs-refinement = a real proposition or direction exists, but scope, actor, mechanism, or target is still unclear.\n"
    "- ballot-ready can include a clearly stated constitutional, legal, or policy rule, even when phrased as a question.\n"
    "- policy_topic is UI metadata only.\n"
    "- policy_key must be stance-neutral, lowercase-with-hyphens, and represent one ballot-level issue.\n"
    "- For actor_scope, action_mechanism, and target_scope, use other when the dimension is clear but outside the listed buckets; use unclear only when it is genuinely unclear.\n"
    "- Do not merge distinct propositions. Create a new policy_key when actor, mechanism, or target materially differs, "
    "or when reuse would change ballot wording, option sets, or refinement output.\n"
    "- For compound submissions, keep only the dominant proposition in policy_key/title/summary. "
    "Put secondary ideas in ambiguity_flags or ballot_readiness_reason, and use compound_submission when appropriate.\n"
    "Return JSON only with fields:\n"
    f"is_valid_policy, rejection_reason, title, summary, stance ({_STANCES}), policy_topic, "
    "policy_key, actor_scope, action_mechanism, target_scope, ballot_readiness, "
    "ballot_readiness_reason, entities, confidence, ambiguity_flags.\n"
    "actor_scope: domestic-citizens, foreign-state, international-organization, civil-society, public-governance, other, unclear.\n"
    "action_mechanism: labor-strike, economic-sanctions, economic-pressure, military-action, diplomatic-pressure, "
    "civil-society-support, governance-design, discussion-only, other, unclear.\n"
    "target_scope: iranian-regime, iranian-economy, public-governance, civil-rights, other, unclear.\n"
    "ballot_readiness: ballot-ready, needs-refinement, discussion-only.\n"
    "If invalid, set policy_topic=policy_key=unassigned, actor_scope/action_mechanism/target_scope=unclear, "
    "ballot_readiness=discussion-only, confidence=0.\n"
)

_INSTRUCTION_VERSION = hashlib.sha256(_CANONICALIZATION_INSTRUCTIONS.encode("utf-8")).hexdigest()[:16]


def _prompt_for_item(item: dict[str, Any], policy_context: str = "") -> str:
    context_block = ""
    if policy_context:
        context_block = (
            "\nExisting open policy keys (reuse only if actor, mechanism, and target materially match):\n"
            f"{policy_context}\n"
            "Reuse only on a true actor/mechanism/target match. "
            "If actor or mechanism differs, create a new policy_key. "
            "Also create a new key whenever reuse would change the ballot-level proposition, wording, or option set.\n\n"
        )
    return (
        _CANONICALIZATION_INSTRUCTIONS
        + context_block
        + f"\nInput: {json.dumps(item, ensure_ascii=False)}"
    )


@dataclass(slots=True)
class CanonicalizationRejection:
    reason: str
    model_version: str
    prompt_version: str


def _prompt_version(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


_FARSI_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_SCRIPT_RE = re.compile(r"[A-Za-z]")
_BROAD_CONFLICT_TERM_RE = re.compile(r"(war|conflict|intervention|military|جنگ|درگیری|مداخله|نظامی)", flags=re.IGNORECASE)
_EXPLICIT_IRANIAN_REGIME_TARGET_RE = re.compile(
    r"(regime|regime change|government of iran|iranian government|حکومت|رژیم|دولت)",
    flags=re.IGNORECASE,
)


def _default_rejection_reason(language: str) -> str:
    if language.lower().startswith("fa"):
        return "این متن به اندازه کافی مشخص نیست که به عنوان یک پیشنهاد سیاستی در نظر گرفته شود."
    return "This submission is not specific enough to be treated as a policy proposal."


def _normalize_rejection_reason(reason: object, *, language: str) -> tuple[str, bool]:
    text = str(reason or "").strip()
    if not text:
        return _default_rejection_reason(language), True

    has_farsi = bool(_FARSI_SCRIPT_RE.search(text))
    has_latin = bool(_LATIN_SCRIPT_RE.search(text))
    normalized_language = language.lower()
    if normalized_language.startswith("fa"):
        if has_latin and not has_farsi:
            return _default_rejection_reason(language), True
        return text, False
    if has_farsi and not has_latin:
        return _default_rejection_reason(language), True
    return text, False


def _should_downgrade_target_scope(*, raw_text: str, target_scope: str) -> bool:
    if target_scope != "iranian-regime":
        return False
    if not _BROAD_CONFLICT_TERM_RE.search(raw_text):
        return False
    return _EXPLICIT_IRANIAN_REGIME_TARGET_RE.search(raw_text) is None


def _parse_candidate_payload(payload: str) -> tuple[dict[str, Any], str | None]:
    """Parse LLM output JSON. Returns (data, repair_method) where repair_method
    is None for clean parse or ``"regex"`` when local regex repair was applied."""
    text = payload.strip()
    if "```" in text:
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
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
        repaired = re.sub(r'(?<=")\s+(?=")', ", ", repaired)
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
    raw_text: str,
) -> PolicyCandidateCreate:
    """Build a PolicyCandidateCreate from parsed LLM output."""
    confidence = float(output.get("confidence", 0.0))
    raw_flags = output.get("ambiguity_flags")
    flags = list(raw_flags) if isinstance(raw_flags, list) else []
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

    if _should_downgrade_target_scope(raw_text=raw_text, target_scope=target_scope):
        target_scope = _DEFAULT_TARGET_SCOPE
        if "target_scope_unclear_from_input" not in flags:
            flags.append("target_scope_unclear_from_input")

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
        reason, normalized_reason = _normalize_rejection_reason(parsed.get("rejection_reason"), language=language)
        await append_evidence(
            session=session,
            event_type="submission_rejected_not_policy",
            entity_type="submission",
            entity_id=submission_id,
            payload={
                "submission_id": str(submission_id),
                "rejection_reason": reason,
                "rejection_reason_language_normalized": normalized_reason,
                "model_version": parsed["model_version"],
                "prompt_version": parsed["prompt_version"],
            },
        )
        return CanonicalizationRejection(
            reason=reason,
            model_version=str(parsed["model_version"]),
            prompt_version=str(parsed["prompt_version"]),
        )

    candidate = _build_candidate_create(parsed, submission_id, raw_text=raw_text)
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
            reason, normalized_reason = _normalize_rejection_reason(
                output.get("rejection_reason"),
                language=str(submissions[idx].get("language", "en")),
            )
            await append_evidence(
                session=session,
                event_type="submission_rejected_not_policy",
                entity_type="submission",
                entity_id=submissions[idx]["id"],
                payload={
                    "submission_id": str(submissions[idx]["id"]),
                    "rejection_reason": reason,
                    "rejection_reason_language_normalized": normalized_reason,
                    "model_version": str(output.get("model_version", "")),
                    "prompt_version": str(output.get("prompt_version", "")),
                },
            )
            continue

        candidate = _build_candidate_create(
            output,
            submissions[idx]["id"],
            raw_text=str(submissions[idx].get("raw_text", "")),
        )
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
