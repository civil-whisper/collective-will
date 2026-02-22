from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.evidence import EvidenceLogEntry, append_evidence
from src.db.queries import create_policy_candidate
from src.models.submission import PolicyCandidate, PolicyCandidateCreate, PolicyDomain, Submission
from src.pipeline.llm import LLMResponse, LLMRouter

logger = logging.getLogger(__name__)

_DOMAINS = "governance, economy, rights, foreign_policy, religion, ethnic, justice, other"
_STANCES = "support, oppose, neutral, unclear"


def _prompt_version(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _build_dispute_prompt(*, submission: Submission, current_candidate: PolicyCandidate | None) -> str:
    current_block = ""
    if current_candidate is not None:
        current_block = (
            "Current canonicalization (possibly disputed):\n"
            f"- title: {current_candidate.title}\n"
            f"- domain: {current_candidate.domain.value}\n"
            f"- summary: {current_candidate.summary}\n"
            f"- stance: {current_candidate.stance}\n"
            f"- confidence: {current_candidate.confidence}\n"
        )
    return (
        "You are resolving a user dispute about canonicalization.\n"
        "Re-canonicalize ONLY this disputed submission into strict JSON.\n"
        "Required keys: title, domain, summary, stance, entities, confidence, ambiguity_flags.\n"
        f"Allowed domain values: {_DOMAINS}.\n"
        f"Allowed stance values: {_STANCES}.\n"
        "Return ONLY raw JSON object.\n"
        f"{current_block}\n"
        f'Disputed submission text: {json.dumps(submission.raw_text, ensure_ascii=False)}'
    )


def _parse_candidate_payload(payload: str) -> dict[str, Any]:
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
    data = json.loads(text)
    if isinstance(data, list):
        return cast(dict[str, Any], data[0])
    return cast(dict[str, Any], data)


def _normalize_decision(raw: dict[str, Any], completion: LLMResponse, prompt: str) -> dict[str, Any]:
    domain_value = str(raw.get("domain", "other")).strip()
    if domain_value not in {member.value for member in PolicyDomain}:
        domain_value = "other"

    stance_raw = str(raw.get("stance", "unclear")).lower().strip()
    stance_map = {"supportive": "support", "opposing": "oppose", "opposed": "oppose"}
    stance_value = stance_map.get(stance_raw, stance_raw)
    if stance_value not in {"support", "oppose", "neutral", "unclear"}:
        stance_value = "unclear"

    entities_raw = raw.get("entities", [])
    entities = [str(item) for item in entities_raw] if isinstance(entities_raw, list) else []

    flags_raw = raw.get("ambiguity_flags", [])
    flags = [str(item) for item in flags_raw] if isinstance(flags_raw, list) else []

    confidence = float(raw.get("confidence", 0.0))
    if confidence < 0.0:
        confidence = 0.0
    if confidence > 1.0:
        confidence = 1.0
    if confidence < 0.7 and "low_confidence" not in flags:
        flags.append("low_confidence")

    return {
        "title": str(raw.get("title", "Untitled policy candidate")),
        "domain": domain_value,
        "summary": str(raw.get("summary", "")),
        "stance": stance_value,
        "entities": entities,
        "confidence": confidence,
        "ambiguity_flags": flags,
        "model_version": completion.model,
        "prompt_version": _prompt_version(prompt),
    }


async def _record_dispute_metrics(
    *,
    session: AsyncSession,
    submission_id: Any,
    resolution_seconds: float | None,
    escalated: bool,
    confidence: float,
) -> None:
    now = datetime.now(UTC)
    lookback_start = now - timedelta(days=7)

    submission_count_result = await session.execute(
        select(func.count(Submission.id)).where(Submission.created_at >= lookback_start)
    )
    submission_count = int(submission_count_result.scalar_one())

    dispute_open_count_result = await session.execute(
        select(func.count(EvidenceLogEntry.id)).where(
            EvidenceLogEntry.event_type == "dispute_opened",
            EvidenceLogEntry.timestamp >= lookback_start,
        )
    )
    dispute_open_count = int(dispute_open_count_result.scalar_one())

    dispute_resolved_rows = await session.execute(
        select(EvidenceLogEntry.payload).where(
            EvidenceLogEntry.event_type == "dispute_resolved",
            EvidenceLogEntry.timestamp >= lookback_start,
        )
    )
    resolved_payloads = list(dispute_resolved_rows.scalars().all())
    resolved_count = len(resolved_payloads)
    escalated_count = sum(1 for item in resolved_payloads if bool(item.get("escalated")))

    dispute_rate = dispute_open_count / submission_count if submission_count > 0 else 0.0
    disagreement_rate = escalated_count / resolved_count if resolved_count > 0 else 0.0

    await append_evidence(
        session=session,
        event_type="dispute_metrics_recorded",
        entity_type="dispute",
        entity_id=submission_id,
        payload={
            "lookback_days": 7,
            "submission_count": submission_count,
            "dispute_open_count": dispute_open_count,
            "resolved_count": resolved_count,
            "escalated_count": escalated_count,
            "dispute_rate": dispute_rate,
            "disagreement_rate": disagreement_rate,
            "resolution_seconds": resolution_seconds,
            "latest_escalated": escalated,
            "latest_confidence": confidence,
        },
    )

    if dispute_rate > 0.05 or disagreement_rate > 0.30:
        await append_evidence(
            session=session,
            event_type="dispute_tuning_recommended",
            entity_type="dispute",
            entity_id=submission_id,
            payload={
                "thresholds": {"dispute_rate": 0.05, "disagreement_rate": 0.30},
                "observed": {"dispute_rate": dispute_rate, "disagreement_rate": disagreement_rate},
                "recommended_action": "tune_model_prompt_policy",
            },
        )


async def _run_ensemble(
    *,
    llm_router: LLMRouter,
    prompt: str,
    models: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    for model in models:
        try:
            completion = await llm_router.complete_with_model(model=model, prompt=prompt, temperature=0.1)
            parsed = _parse_candidate_payload(completion.text)
            decisions.append(_normalize_decision(parsed, completion, prompt))
        except Exception:
            logger.exception("Dispute ensemble model failed: %s", model)
    if not decisions:
        raise RuntimeError("Dispute ensemble failed: no model succeeded")
    best = max(decisions, key=lambda item: float(item.get("confidence", 0.0)))
    return best, decisions


async def resolve_submission_dispute(
    *,
    session: AsyncSession,
    submission: Submission,
    llm_router: LLMRouter | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    router = llm_router or LLMRouter(settings=settings)
    candidate_result = await session.execute(
        select(PolicyCandidate)
        .where(PolicyCandidate.submission_id == submission.id)
        .order_by(PolicyCandidate.created_at.desc())
        .limit(1)
    )
    current_candidate = candidate_result.scalars().first()
    open_entry_result = await session.execute(
        select(EvidenceLogEntry)
        .where(
            EvidenceLogEntry.entity_type == "dispute",
            EvidenceLogEntry.entity_id == submission.id,
            EvidenceLogEntry.event_type == "dispute_opened",
        )
        .order_by(EvidenceLogEntry.id.desc())
        .limit(1)
    )
    open_entry = open_entry_result.scalars().first()

    prompt = _build_dispute_prompt(submission=submission, current_candidate=current_candidate)
    primary_completion = await router.complete(tier="dispute_resolution", prompt=prompt)
    primary_parsed = _parse_candidate_payload(primary_completion.text)
    primary_decision = _normalize_decision(primary_parsed, primary_completion, prompt)
    final_decision = primary_decision
    escalated = False

    if primary_decision["confidence"] < settings.dispute_resolution_confidence_threshold:
        escalated = True
        ensemble_models = settings.dispute_ensemble_model_list()
        final_decision, ensemble_decisions = await _run_ensemble(
            llm_router=router,
            prompt=prompt,
            models=ensemble_models,
        )
        await append_evidence(
            session=session,
            event_type="dispute_escalated",
            entity_type="dispute",
            entity_id=submission.id,
            payload={
                "state": "dispute_escalated",
                "threshold": settings.dispute_resolution_confidence_threshold,
                "primary_model": primary_decision["model_version"],
                "primary_confidence": primary_decision["confidence"],
                "ensemble_models": ensemble_models,
                "selected_model": final_decision["model_version"],
                "selected_confidence": final_decision["confidence"],
                "ensemble_count": len(ensemble_decisions),
            },
        )

    resolved_candidate: PolicyCandidate
    if current_candidate is None:
        resolved_candidate = await create_policy_candidate(
            session,
            PolicyCandidateCreate(
                submission_id=submission.id,
                title=final_decision["title"],
                title_en=None,
                domain=PolicyDomain(final_decision["domain"]),
                summary=final_decision["summary"],
                summary_en=None,
                stance=final_decision["stance"],
                entities=final_decision["entities"],
                embedding=None,
                confidence=final_decision["confidence"],
                ambiguity_flags=final_decision["ambiguity_flags"],
                model_version=final_decision["model_version"],
                prompt_version=final_decision["prompt_version"],
            ),
        )
    else:
        current_candidate.title = final_decision["title"]
        current_candidate.domain = PolicyDomain(final_decision["domain"])
        current_candidate.summary = final_decision["summary"]
        current_candidate.stance = final_decision["stance"]
        current_candidate.entities = final_decision["entities"]
        current_candidate.confidence = final_decision["confidence"]
        current_candidate.ambiguity_flags = final_decision["ambiguity_flags"]
        current_candidate.model_version = final_decision["model_version"]
        current_candidate.prompt_version = final_decision["prompt_version"]
        resolved_candidate = current_candidate

    await append_evidence(
        session=session,
        event_type="dispute_resolved",
        entity_type="dispute",
        entity_id=submission.id,
        payload={
            "state": "dispute_resolved",
            "submission_id": str(submission.id),
            "candidate_id": str(resolved_candidate.id),
            "escalated": escalated,
            "confidence": final_decision["confidence"],
            "model_version": final_decision["model_version"],
            "resolution_seconds": (
                (datetime.now(UTC) - open_entry.timestamp).total_seconds()
                if open_entry is not None
                else None
            ),
        },
    )
    await _record_dispute_metrics(
        session=session,
        submission_id=submission.id,
        resolution_seconds=(
            (datetime.now(UTC) - open_entry.timestamp).total_seconds()
            if open_entry is not None
            else None
        ),
        escalated=escalated,
        confidence=final_decision["confidence"],
    )
    await session.commit()
    return {
        "status": "resolved",
        "submission_id": str(submission.id),
        "candidate_id": str(resolved_candidate.id),
        "escalated": escalated,
        "confidence": final_decision["confidence"],
    }
