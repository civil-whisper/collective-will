from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.submission import PolicyCandidateCreate, PolicyDomain
from src.pipeline.llm import LLMRouter
from src.pipeline.privacy import prepare_batch_for_llm, re_link_results, validate_no_metadata

_DOMAINS = "governance, economy, rights, foreign_policy, religion, ethnic, justice, other"
_STANCES = "support, oppose, neutral, unclear"

_SYSTEM_PROMPT = (
    "You are processing civic submissions for a democratic deliberation platform. "
    "Citizens submit policy ideas, concerns, or questions in any language (often Farsi "
    "or English). Your job is to determine whether the input relates to a civic or "
    "policy topic and, if so, convert it into canonical structured form. All canonical "
    "output (title, summary, entities) must be in English regardless of the input language."
)


def _prompt_for_item(item: dict[str, Any]) -> str:
    return (
        "Evaluate and canonicalize this civic submission into structured JSON.\n\n"
        "LANGUAGE RULES:\n"
        "- Detect the input language automatically.\n"
        "- title, summary, and entities MUST always be in English "
        "(translate if the input is in another language).\n"
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
        "Required JSON fields:\n"
        "  is_valid_policy (bool): true if valid civic/policy proposal, false otherwise,\n"
        "  rejection_reason (str or null): if invalid, explain in the INPUT language,\n"
        f"  title (str, ENGLISH), domain (one of: {_DOMAINS}),\n"
        f"  summary (str, ENGLISH), stance (one of: {_STANCES}),\n"
        "  entities (list of strings, ENGLISH), confidence (float 0-1), "
        "ambiguity_flags (list of strings).\n\n"
        "If is_valid_policy is false, still fill title/summary/domain with best-effort "
        "English values but set confidence to 0.\n"
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


def _parse_candidate_payload(payload: str) -> dict[str, Any]:
    text = payload.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
        if text.endswith("```"):
            text = text[:-3].rstrip()
    # Some models wrap JSON in prose; extract the first { ... } block
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
    data = json.loads(text)
    if isinstance(data, list):
        return cast(dict[str, Any], data[0])
    return cast(dict[str, Any], data)


def _build_candidate_create(
    output: dict[str, Any],
    submission_id: UUID,
) -> PolicyCandidateCreate:
    """Build a PolicyCandidateCreate from parsed LLM output."""
    confidence = float(output.get("confidence", 0.0))
    flags = list(output.get("ambiguity_flags", []))
    if confidence < 0.7 and "low_confidence" not in flags:
        flags.append("low_confidence")

    domain_value = output.get("domain", "other")
    if domain_value not in {member.value for member in PolicyDomain}:
        domain_value = "other"

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

    return PolicyCandidateCreate(
        submission_id=submission_id,
        title=str(output.get("title", "Untitled policy candidate")),
        domain=PolicyDomain(domain_value),
        summary=str(output.get("summary", "")),
        stance=stance,
        entities=entities,
        confidence=confidence,
        ambiguity_flags=flags,
        model_version=str(output["model_version"]),
        prompt_version=str(output["prompt_version"]),
        title_en=output.get("title_en"),
        summary_en=output.get("summary_en"),
        embedding=None,
    )


async def canonicalize_single(
    *,
    session: AsyncSession,
    submission_id: UUID,
    raw_text: str,
    language: str,
    llm_router: LLMRouter,
) -> PolicyCandidateCreate | CanonicalizationRejection:
    """Canonicalize one submission inline. Returns candidate data or rejection."""
    sanitized, _ = prepare_batch_for_llm([{"raw_text": raw_text, "language": language}])
    if not validate_no_metadata(sanitized):
        raise ValueError("Sanitized payload still contains metadata")

    item = sanitized[0]
    prompt = _prompt_for_item(item)
    completion = await llm_router.complete(
        tier="canonicalization", prompt=prompt, system_prompt=_SYSTEM_PROMPT,
    )
    parsed = _parse_candidate_payload(completion.text)
    parsed["model_version"] = completion.model
    parsed["prompt_version"] = _prompt_version(prompt)

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
            "domain": candidate.domain.value,
            "stance": candidate.stance,
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
) -> list[PolicyCandidateCreate]:
    sanitized, index_map = prepare_batch_for_llm(submissions)
    if not validate_no_metadata(sanitized):
        raise ValueError("Sanitized payload still contains metadata")

    llm_outputs: list[dict[str, Any]] = []
    for item in sanitized:
        prompt = _prompt_for_item(item)
        completion = await llm_router.complete(
            tier="canonicalization", prompt=prompt, system_prompt=_SYSTEM_PROMPT,
        )
        parsed = _parse_candidate_payload(completion.text)
        parsed["model_version"] = completion.model
        parsed["prompt_version"] = _prompt_version(prompt)
        llm_outputs.append(parsed)

    ordered = re_link_results(llm_outputs, index_map)
    candidates: list[PolicyCandidateCreate] = []
    for idx, output in enumerate(ordered):
        if not output.get("is_valid_policy", True):
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
                "domain": candidate.domain.value,
                "stance": candidate.stance,
                "confidence": candidate.confidence,
                "model_version": candidate.model_version,
                "prompt_version": candidate.prompt_version,
            },
        )

    return candidates
