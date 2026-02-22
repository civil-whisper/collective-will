from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.submission import PolicyCandidateCreate, PolicyDomain
from src.pipeline.llm import LLMRouter
from src.pipeline.privacy import prepare_batch_for_llm, re_link_results, validate_no_metadata


def _prompt_for_item(item: dict[str, Any]) -> str:
    return (
        "Convert this Farsi civic submission into canonical structured JSON with fields:\n"
        "title, domain, summary, stance, entities, confidence, ambiguity_flags.\n"
        f"Input: {json.dumps(item, ensure_ascii=False)}"
    )


def _prompt_version(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _parse_candidate_payload(payload: str) -> dict[str, Any]:
    data = json.loads(payload)
    if isinstance(data, list):
        return cast(dict[str, Any], data[0])
    return cast(dict[str, Any], data)


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
        completion = await llm_router.complete(tier="canonicalization", prompt=prompt)
        parsed = _parse_candidate_payload(completion.text)
        parsed["model_version"] = completion.model
        parsed["prompt_version"] = _prompt_version(prompt)
        llm_outputs.append(parsed)

    ordered = re_link_results(llm_outputs, index_map)
    candidates: list[PolicyCandidateCreate] = []
    for idx, output in enumerate(ordered):
        confidence = float(output.get("confidence", 0.0))
        flags = list(output.get("ambiguity_flags", []))
        if confidence < 0.7 and "low_confidence" not in flags:
            flags.append("low_confidence")

        domain_value = output.get("domain", "other")
        if domain_value not in {member.value for member in PolicyDomain}:
            domain_value = "other"

        candidate = PolicyCandidateCreate(
            submission_id=submissions[idx]["id"],
            title=str(output.get("title", "Untitled policy candidate")),
            domain=PolicyDomain(domain_value),
            summary=str(output.get("summary", "")),
            stance=str(output.get("stance", "unclear")),
            entities=[str(v) for v in output.get("entities", [])],
            confidence=confidence,
            ambiguity_flags=flags,
            model_version=str(output["model_version"]),
            prompt_version=str(output["prompt_version"]),
            title_en=output.get("title_en"),
            summary_en=output.get("summary_en"),
            embedding=None,
        )
        candidates.append(candidate)
        await append_evidence(
            session=session,
            event_type="candidate_created",
            entity_type="submission",
            entity_id=submissions[idx]["id"],
            payload={
                "title": candidate.title,
                "domain": candidate.domain.value,
                "confidence": candidate.confidence,
                "model_version": candidate.model_version,
                "prompt_version": candidate.prompt_version,
            },
        )

    return candidates
