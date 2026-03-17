from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import load_only

from src.config import Settings, get_settings
from src.models.submission import Submission
from src.pipeline.canonicalize import (
    _INSTRUCTION_VERSION,
    _build_candidate_create,
    _normalize_rejection_reason,
    _parse_candidate_payload_with_repair,
    _prompt_for_item,
    _prompt_version,
)
from src.pipeline.canonicalize import (
    _SYSTEM_PROMPT as CANONICALIZATION_SYSTEM_PROMPT,
)
from src.pipeline.embeddings import prepare_text_for_embedding
from src.pipeline.endorsement import (
    _PROMPT_TEMPLATE as BALLOT_PROMPT_TEMPLATE,
)
from src.pipeline.endorsement import (
    _SYSTEM_PROMPT as BALLOT_SYSTEM_PROMPT,
)
from src.pipeline.endorsement import (
    _build_submissions_block as _build_ballot_submissions_block,
)
from src.pipeline.endorsement import _parse_ballot_response, _sanitize_ballot_wording
from src.pipeline.llm import EmbeddingResult, LLMResponse, LLMRouter
from src.pipeline.normalize import (
    _REMAP_PROMPT_TEMPLATE,
    _REMAP_SYSTEM_PROMPT,
    _cluster_by_embedding,
    _entries_are_merge_compatible,
    _extract_merges_from_mapping,
    _parse_remap_response,
    _same_key_group_needs_revalidation,
)
from src.pipeline.normalize import (
    _build_submissions_block as _build_normalization_submissions_block,
)
from src.pipeline.normalize import review_same_key_reuse
from src.pipeline.options import (
    _fallback_options,
    _generate_options_for_cluster,
)
from src.pipeline.privacy import prepare_batch_for_llm, validate_no_metadata
from src.pipeline.refinement import (
    _PROMPT_TEMPLATE as REFINEMENT_PROMPT_TEMPLATE,
)
from src.pipeline.refinement import (
    _SYSTEM_PROMPT as REFINEMENT_SYSTEM_PROMPT,
)
from src.pipeline.refinement import _build_submissions_block as _build_refinement_submissions_block
from src.pipeline.refinement import _parse_refinement_payload, _sanitize_refinement_output


@dataclass(slots=True)
class ReplaySubmissionInput:
    raw_text: str
    language: str
    source_submission_id: str | None = None
    original_status: str | None = None
    created_at: str | None = None
    replay_submission_id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class ReplayCandidate:
    id: UUID
    submission_id: UUID
    source_submission_id: str | None
    raw_text: str
    language: str
    title: str
    summary: str
    stance: str
    policy_topic: str
    policy_key: str
    actor_scope: str
    action_mechanism: str
    target_scope: str
    ballot_readiness: str
    ballot_readiness_reason: str | None
    entities: list[str]
    confidence: float
    ambiguity_flags: list[str]
    model_version: str
    prompt_version: str
    embedding: list[float] | None = None


@dataclass(slots=True)
class ReplayDegradationEvent:
    step: str
    entity_id: str | None
    event_type: str
    detail: str
    model: str | None = None
    fallback_from: str | None = None


@dataclass(slots=True)
class ReplayCluster:
    id: UUID
    policy_key: str
    policy_topic: str
    candidate_ids: list[UUID]
    member_count: int
    summary: str = ""
    ballot_question: str | None = None
    ballot_question_fa: str | None = None
    refinement_draft: str | None = None
    refinement_draft_fa: str | None = None
    refinement_confidence: float | None = None
    refinement_requires_clarification: bool | None = None
    refinement_notes: str | None = None
    options: list[dict[str, str]] = field(default_factory=list)


def dataset_fingerprint(submissions: list[ReplaySubmissionInput]) -> str:
    material = json.dumps(
        [
            {
                "raw_text": item.raw_text,
                "language": item.language,
                "source_submission_id": item.source_submission_id,
                "original_status": item.original_status,
            }
            for item in submissions
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _cache_key(prefix: str, payload: str) -> str:
    return hashlib.sha256(f"{prefix}::{payload}".encode()).hexdigest()


class ReplayCachingLLMRouter(LLMRouter):
    """LLM router with incremental on-disk caching for replay runs."""

    def __init__(self, *, cache_path: Path, settings: Settings | None = None) -> None:
        super().__init__(settings=settings)
        self.cache_path = cache_path
        self._cache = self._load_cache(cache_path)
        self.cache_hits = 0
        self.cache_misses = 0

    @staticmethod
    def _load_cache(path: Path) -> dict[str, Any]:
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                data = json.load(fh)
            data.setdefault("completions", {})
            data.setdefault("embeddings", {})
            data.setdefault("dataset_fingerprint", "")
            return data
        return {"completions": {}, "embeddings": {}, "dataset_fingerprint": ""}

    def save(self, *, fingerprint: str | None = None) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        if fingerprint is not None:
            self._cache["dataset_fingerprint"] = fingerprint
        with gzip.open(self.cache_path, "wt", encoding="utf-8") as fh:
            json.dump(self._cache, fh, ensure_ascii=False, separators=(",", ":"))

    async def complete(
        self,
        *,
        tier: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_s: float | None = None,
        grounding: bool = False,
    ) -> LLMResponse:
        primary_model, fallback_model = self._resolve_tier_models(tier)
        cache_payload = json.dumps(
            {
                "tier": tier,
                "primary_model": primary_model,
                "fallback_model": fallback_model,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "grounding": grounding,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        key = _cache_key("completion", cache_payload)
        cached = self._cache["completions"].get(key)
        if cached is not None:
            self.cache_hits += 1
            payload = {
                field_name: cached[field_name]
                for field_name in LLMResponse.model_fields
                if field_name in cached
            }
            return LLMResponse(**payload)

        self.cache_misses += 1
        response = await super().complete(
            tier=tier,  # type: ignore[arg-type]
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
            grounding=grounding,
        )
        self._cache["completions"][key] = {
            "tier": tier,
            "grounding": grounding,
            **response.model_dump(),
        }
        self.save()
        return response

    async def embed(self, texts: list[str], timeout_s: float | None = None) -> EmbeddingResult:
        vectors: list[list[float]] = []
        missing: list[tuple[int, str, str]] = []
        for idx, text in enumerate(texts):
            key = _cache_key(
                "embedding",
                json.dumps(
                    {
                        "embedding_model": self.settings.embedding_model,
                        "embedding_fallback_model": self.settings.embedding_fallback_model,
                        "text": text,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            cached = self._cache["embeddings"].get(key)
            if cached is None:
                missing.append((idx, key, text))
                vectors.append([])
            else:
                self.cache_hits += 1
                vectors.append([float(value) for value in cached])

        if missing:
            self.cache_misses += len(missing)
            live_vectors = await super().embed([text for _, _, text in missing], timeout_s=timeout_s)
            for (idx, key, _text), vector in zip(missing, live_vectors.vectors, strict=True):
                rounded = [round(value, 6) for value in vector]
                self._cache["embeddings"][key] = rounded
                vectors[idx] = rounded
            self.save()

        return EmbeddingResult(vectors=vectors, model="replay-cache", provider="cache")

    async def complete_with_model(
        self,
        *,
        tier: str | None = None,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_s: float | None = None,
        grounding: bool = False,
    ) -> LLMResponse:
        cache_payload = json.dumps(
            {
                "tier": tier,
                "model": model,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "grounding": grounding,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        key = _cache_key("completion_with_model", cache_payload)
        cached = self._cache["completions"].get(key)
        if cached is not None:
            self.cache_hits += 1
            payload = {
                field_name: cached[field_name]
                for field_name in LLMResponse.model_fields
                if field_name in cached
            }
            return LLMResponse(**payload)

        self.cache_misses += 1
        response = await super().complete_with_model(
            tier=tier,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
            grounding=grounding,
        )
        self._cache["completions"][key] = {
            "tier": tier,
            "grounding": grounding,
            **response.model_dump(),
        }
        self.save()
        return response

    def stats(self) -> dict[str, Any]:
        completions = list(self._cache["completions"].values())
        by_model: dict[str, dict[str, int | float]] = {}
        largest_calls = sorted(
            (
                {
                    "tier": item.get("tier"),
                    "model": item.get("model"),
                    "grounding": bool(item.get("grounding", False)),
                    "input_tokens": int(item.get("input_tokens", 0)),
                    "output_tokens": int(item.get("output_tokens", 0)),
                    "cost_usd": round(float(item.get("cost_usd", 0.0)), 6),
                    "fallback_from": item.get("fallback_from"),
                }
                for item in completions
            ),
            key=lambda item: (item["cost_usd"], item["input_tokens"] + item["output_tokens"]),
            reverse=True,
        )[:5]
        for item in completions:
            model = str(item.get("model", "unknown"))
            bucket = by_model.setdefault(
                model,
                {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
            )
            bucket["calls"] = int(bucket["calls"]) + 1
            bucket["input_tokens"] = int(bucket["input_tokens"]) + int(item.get("input_tokens", 0))
            bucket["output_tokens"] = int(bucket["output_tokens"]) + int(item.get("output_tokens", 0))
            bucket["cost_usd"] = float(bucket["cost_usd"]) + float(item.get("cost_usd", 0.0))

        total_cache_read = sum(int(item.get("cache_read_tokens", 0)) for item in completions)
        total_cache_write = sum(int(item.get("cache_write_tokens", 0)) for item in completions)
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "live_cost_usd": round(self.total_cost_usd, 6),
            "total_cost_usd": round(sum(float(item.get("cost_usd", 0.0)) for item in completions), 6),
            "completion_call_count": len(completions),
            "embedding_call_count": len(self._cache["embeddings"]),
            "grounded_call_count": sum(1 for item in completions if item.get("grounding")),
            "provider_cache_read_tokens": total_cache_read,
            "provider_cache_write_tokens": total_cache_write,
            "instruction_version": _INSTRUCTION_VERSION,
            "cost_by_model_usd": {
                model: round(float(bucket["cost_usd"]), 6)
                for model, bucket in sorted(by_model.items())
            },
            "tokens_by_model": {
                model: {
                    "calls": int(bucket["calls"]),
                    "input_tokens": int(bucket["input_tokens"]),
                    "output_tokens": int(bucket["output_tokens"]),
                    "total_tokens": int(bucket["input_tokens"]) + int(bucket["output_tokens"]),
                }
                for model, bucket in sorted(by_model.items())
            },
            "largest_calls": largest_calls,
            "dataset_fingerprint": self._cache.get("dataset_fingerprint", ""),
        }


class PolicyContextAccumulator:
    def __init__(self) -> None:
        self._data: dict[str, tuple[int, str]] = {}

    def add(self, policy_key: str, summary: str) -> None:
        if policy_key == "unassigned":
            return
        clean_summary = (summary or "").replace("\n", " ")
        if policy_key in self._data:
            count, existing_summary = self._data[policy_key]
            self._data[policy_key] = (count + 1, existing_summary)
        else:
            self._data[policy_key] = (1, clean_summary)

    def rebuild(self, candidates: list[ReplayCandidate]) -> None:
        self._data = {}
        for candidate in candidates:
            self.add(candidate.policy_key, candidate.summary)

    def format_context(self) -> str:
        if not self._data:
            return ""
        lines: list[str] = []
        for key, (count, summary) in sorted(self._data.items(), key=lambda item: (-item[1][0], item[0])):
            lines.append(f'  - "{key}" ({count} submissions) — {summary}')
        return "\n".join(lines)


async def load_submissions_from_db(
    *,
    database_url: str | None = None,
    limit: int | None = None,
) -> list[ReplaySubmissionInput]:
    settings = get_settings()
    engine = create_async_engine(database_url or settings.database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            stmt = (
                select(Submission)
                .options(load_only(Submission.id, Submission.raw_text, Submission.language, Submission.status, Submission.created_at))
                .order_by(Submission.created_at.asc(), Submission.id.asc())
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = list((await session.execute(stmt)).scalars().all())
            return [
                ReplaySubmissionInput(
                    raw_text=item.raw_text,
                    language=item.language,
                    source_submission_id=str(item.id),
                    original_status=item.status,
                    created_at=item.created_at.isoformat(),
                )
                for item in rows
            ]
    finally:
        await engine.dispose()


def load_submissions_from_json(path: Path, *, limit: int | None = None) -> list[ReplaySubmissionInput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("submissions")
    if not isinstance(payload, list):
        raise ValueError("Submission snapshot JSON must be a list or an object with a 'submissions' list")

    submissions: list[ReplaySubmissionInput] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw_text = item.get("raw_text")
        language = item.get("language", "fa")
        if not isinstance(raw_text, str) or not isinstance(language, str):
            continue
        submissions.append(
            ReplaySubmissionInput(
                raw_text=raw_text,
                language=language,
                source_submission_id=str(item["id"]) if item.get("id") else None,
                original_status=str(item["status"]) if item.get("status") else None,
                created_at=str(item["created_at"]) if item.get("created_at") else None,
            )
        )
        if limit is not None and len(submissions) >= limit:
            break
    return submissions


def write_submission_snapshot(path: Path, submissions: list[ReplaySubmissionInput]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "id": item.source_submission_id,
                    "raw_text": item.raw_text,
                    "language": item.language,
                    "status": item.original_status,
                    "created_at": item.created_at,
                }
                for item in submissions
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


async def replay_submissions(
    *,
    submissions: list[ReplaySubmissionInput],
    llm_router: LLMRouter,
) -> dict[str, Any]:
    if not submissions:
        return {
            "submission_count": 0,
            "rejected_count": 0,
            "cluster_count": 0,
            "submissions": [],
            "clusters": [],
            "degradation_events": [],
        }

    accumulator = PolicyContextAccumulator()
    candidates: list[ReplayCandidate] = []
    rejected: list[dict[str, Any]] = []
    degradations: list[ReplayDegradationEvent] = []

    for item in submissions:
        prepared, _index_map = prepare_batch_for_llm([{"raw_text": item.raw_text, "language": item.language}])
        if not validate_no_metadata(prepared):
            raise ValueError("Sanitized payload still contains metadata")
        prompt = _prompt_for_item(prepared[0], policy_context=accumulator.format_context() or " ")
        completion = await llm_router.complete(
            tier="canonicalization",
            prompt=prompt,
            system_prompt=CANONICALIZATION_SYSTEM_PROMPT,
        )
        if completion.primary_model_failed:
            degradations.append(ReplayDegradationEvent(
                step="canonicalization",
                entity_id=item.source_submission_id,
                event_type="model_fallback",
                detail=f"Primary model failed, used {completion.model}",
                model=completion.model,
                fallback_from=completion.fallback_from,
            ))
        parsed, repair_method = await _parse_candidate_payload_with_repair(payload=completion.text, llm_router=llm_router)
        if repair_method is not None:
            degradations.append(ReplayDegradationEvent(
                step="canonicalization",
                entity_id=item.source_submission_id,
                event_type="parse_repaired",
                detail=f"Malformed JSON repaired via {repair_method}",
                model=completion.model,
            ))
        parsed["model_version"] = completion.model
        parsed["prompt_version"] = _prompt_version(prompt)
        if not parsed.get("is_valid_policy", True):
            rejection_reason, _ = _normalize_rejection_reason(parsed.get("rejection_reason"), language=item.language)
            rejected.append(
                {
                    "source_submission_id": item.source_submission_id,
                    "raw_text": item.raw_text,
                    "language": item.language,
                    "rejection_reason": rejection_reason,
                    "model_version": completion.model,
                }
            )
            continue
        candidate_create = _build_candidate_create(parsed, item.replay_submission_id, raw_text=item.raw_text)
        candidate = ReplayCandidate(
            id=uuid4(),
            submission_id=item.replay_submission_id,
            source_submission_id=item.source_submission_id,
            raw_text=item.raw_text,
            language=item.language,
            title=candidate_create.title,
            summary=candidate_create.summary,
            stance=candidate_create.stance,
            policy_topic=candidate_create.policy_topic,
            policy_key=candidate_create.policy_key,
            actor_scope=candidate_create.actor_scope,
            action_mechanism=candidate_create.action_mechanism,
            target_scope=candidate_create.target_scope,
            ballot_readiness=candidate_create.ballot_readiness,
            ballot_readiness_reason=candidate_create.ballot_readiness_reason,
            entities=list(candidate_create.entities),
            confidence=candidate_create.confidence,
            ambiguity_flags=list(candidate_create.ambiguity_flags),
            model_version=candidate_create.model_version,
            prompt_version=candidate_create.prompt_version,
        )
        candidates.append(candidate)
        accumulator.add(candidate.policy_key, candidate.summary)

    if candidates:
        candidates = await _revalidate_same_key_candidates_in_memory(candidates, llm_router, degradations)
        embed_result = await llm_router.embed(
            [prepare_text_for_embedding(title=item.title, summary=item.summary) for item in candidates]
        )
        if embed_result.primary_model_failed:
            degradations.append(ReplayDegradationEvent(
                step="embedding",
                entity_id=None,
                event_type="model_fallback",
                detail=f"Primary embedding model failed, used {embed_result.model}",
                model=embed_result.model,
                fallback_from=embed_result.fallback_from,
            ))
        for candidate, vector in zip(candidates, embed_result.vectors, strict=True):
            candidate.embedding = [float(value) for value in vector]
        candidates = await _normalize_candidates_in_memory(candidates, llm_router, degradations)

    clusters = await _build_cluster_reports(candidates, llm_router, degradations)
    grouped = Counter(candidate.policy_key for candidate in candidates if candidate.policy_key != "unassigned")

    degradation_summary: dict[str, int] = Counter()
    for event in degradations:
        degradation_summary[f"{event.step}:{event.event_type}"] += 1

    return {
        "submission_count": len(submissions),
        "candidate_count": len(candidates),
        "rejected_count": len(rejected),
        "cluster_count": len(clusters),
        "degradation_count": len(degradations),
        "degradation_summary": dict(sorted(degradation_summary.items())),
        "group_sizes": dict(sorted(grouped.items(), key=lambda item: (-item[1], item[0]))),
        "rejected": rejected,
        "submissions": [
            {
                "source_submission_id": candidate.source_submission_id,
                "replay_submission_id": str(candidate.submission_id),
                "raw_text": candidate.raw_text,
                "language": candidate.language,
                "policy_topic": candidate.policy_topic,
                "policy_key": candidate.policy_key,
                "title": candidate.title,
                "summary": candidate.summary,
                "stance": candidate.stance,
                "actor_scope": candidate.actor_scope,
                "action_mechanism": candidate.action_mechanism,
                "target_scope": candidate.target_scope,
                "ballot_readiness": candidate.ballot_readiness,
                "ballot_readiness_reason": candidate.ballot_readiness_reason,
                "confidence": candidate.confidence,
                "ambiguity_flags": candidate.ambiguity_flags,
                "model_version": candidate.model_version,
                "prompt_version": candidate.prompt_version,
            }
            for candidate in candidates
        ],
        "degradation_events": [
            {
                "step": event.step,
                "entity_id": event.entity_id,
                "event_type": event.event_type,
                "detail": event.detail,
                "model": event.model,
                "fallback_from": event.fallback_from,
            }
            for event in degradations
        ],
        "clusters": [
            {
                "cluster_id": str(cluster.id),
                "policy_key": cluster.policy_key,
                "policy_topic": cluster.policy_topic,
                "member_count": cluster.member_count,
                "ballot_question": cluster.ballot_question,
                "ballot_question_fa": cluster.ballot_question_fa,
                "summary": cluster.summary,
                "readiness_counts": _readiness_counts(cluster, candidates),
                "refinement_draft": cluster.refinement_draft,
                "refinement_draft_fa": cluster.refinement_draft_fa,
                "refinement_confidence": cluster.refinement_confidence,
                "refinement_requires_clarification": cluster.refinement_requires_clarification,
                "refinement_notes": cluster.refinement_notes,
                "options": cluster.options,
                "members": [
                    {
                        "candidate_id": str(candidate.id),
                        "source_submission_id": candidate.source_submission_id,
                        "raw_text": candidate.raw_text,
                        "title": candidate.title,
                        "summary": candidate.summary,
                        "stance": candidate.stance,
                        "actor_scope": candidate.actor_scope,
                        "action_mechanism": candidate.action_mechanism,
                        "target_scope": candidate.target_scope,
                        "ballot_readiness": candidate.ballot_readiness,
                    }
                    for candidate in candidates
                    if candidate.id in set(cluster.candidate_ids)
                ],
            }
            for cluster in clusters
        ],
    }


async def _normalize_candidates_in_memory(
    candidates: list[ReplayCandidate],
    llm_router: LLMRouter,
    degradations: list[ReplayDegradationEvent],
) -> list[ReplayCandidate]:
    active = [candidate for candidate in candidates if candidate.policy_key != "unassigned" and candidate.embedding is not None]
    if len(active) < 2:
        return candidates

    embeddings = np.array([candidate.embedding for candidate in active], dtype=np.float64)
    labels = _cluster_by_embedding(embeddings)
    groups: dict[int, list[ReplayCandidate]] = defaultdict(list)
    for candidate, label in zip(active, labels, strict=True):
        groups[label].append(candidate)

    for members in groups.values():
        distinct_keys = {candidate.policy_key for candidate in members}
        if len(distinct_keys) < 2:
            continue
        entries = _build_entries_for_replay_cluster(members)
        if not _entries_are_merge_compatible(entries):
            continue
        prompt = _REMAP_PROMPT_TEMPLATE.format(
            submissions_block=_build_normalization_submissions_block(entries)
        )
        try:
            completion = await llm_router.complete(
                tier="english_reasoning",
                prompt=prompt,
                system_prompt=_REMAP_SYSTEM_PROMPT,
                temperature=0.0,
            )
            if completion.primary_model_failed:
                degradations.append(ReplayDegradationEvent(
                    step="normalization",
                    entity_id=None,
                    event_type="model_fallback",
                    detail=f"Primary model failed, used {completion.model}",
                    model=completion.model,
                    fallback_from=completion.fallback_from,
                ))
            key_mapping = _parse_remap_response(completion.text)
        except Exception as exc:
            degradations.append(ReplayDegradationEvent(
                step="normalization",
                entity_id=None,
                event_type="step_failed",
                detail=f"Normalization failed: {type(exc).__name__}: {exc}",
            ))
            continue
        merges = _extract_merges_from_mapping(key_mapping, distinct_keys)
        for survivor_key, doomed_keys in merges.items():
            for candidate in candidates:
                if candidate.policy_key in doomed_keys:
                    candidate.policy_key = survivor_key
    return candidates


async def _revalidate_same_key_candidates_in_memory(
    candidates: list[ReplayCandidate],
    llm_router: LLMRouter,
    degradations: list[ReplayDegradationEvent],
) -> list[ReplayCandidate]:
    groups: dict[str, list[ReplayCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.policy_key != "unassigned":
            groups[candidate.policy_key].append(candidate)

    for key, members in groups.items():
        if len(members) < 2 or not _same_key_group_needs_revalidation(members):
            continue
        try:
            decisions = await review_same_key_reuse(
                policy_key=key,
                existing_members=[],
                new_candidates=members,
                llm_router=llm_router,
            )
        except Exception as exc:
            degradations.append(ReplayDegradationEvent(
                step="same_key_revalidation",
                entity_id=key,
                event_type="step_failed",
                detail=f"Same-key revalidation failed: {type(exc).__name__}: {exc}",
            ))
            continue
        for candidate in members:
            decision = decisions.get(str(candidate.id))
            if decision is None or decision.get("reuse_existing_key", True):
                continue
            new_policy_key = str(decision.get("policy_key", "")).strip()
            new_policy_topic = str(decision.get("policy_topic", "")).strip()
            if not new_policy_key or new_policy_key == candidate.policy_key:
                continue
            candidate.policy_key = new_policy_key
            if new_policy_topic:
                candidate.policy_topic = new_policy_topic
    return candidates


def _build_entries_for_replay_cluster(members: list[ReplayCandidate]) -> list[dict[str, Any]]:
    key_data: dict[str, dict[str, Any]] = {}
    for candidate in members:
        if candidate.policy_key not in key_data:
            key_data[candidate.policy_key] = {
                "key": candidate.policy_key,
                "topic": candidate.policy_topic,
                "count": 1,
                "summaries": [candidate.summary or ""],
                "actor_scope": candidate.actor_scope,
                "action_mechanism": candidate.action_mechanism,
                "target_scope": candidate.target_scope,
                "ballot_readiness": candidate.ballot_readiness,
            }
        else:
            key_data[candidate.policy_key]["count"] += 1
            key_data[candidate.policy_key]["summaries"].append(candidate.summary or "")

    entries: list[dict[str, Any]] = []
    for item in sorted(key_data.values(), key=lambda value: -value["count"]):
        entries.append(
            {
                "key": item["key"],
                "topic": item["topic"],
                "count": item["count"],
                "summary": " | ".join(summary.replace("\n", " ") for summary in item["summaries"] if summary),
                "actor_scope": item["actor_scope"],
                "action_mechanism": item["action_mechanism"],
                "target_scope": item["target_scope"],
                "ballot_readiness": item["ballot_readiness"],
            }
        )
    return entries


async def _build_cluster_reports(
    candidates: list[ReplayCandidate],
    llm_router: LLMRouter,
    degradations: list[ReplayDegradationEvent],
) -> list[ReplayCluster]:
    grouped: dict[str, list[ReplayCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.policy_key != "unassigned":
            grouped[candidate.policy_key].append(candidate)

    clusters: list[ReplayCluster] = []
    candidates_by_id = {candidate.id: candidate for candidate in candidates}
    for policy_key, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        cluster = ReplayCluster(
            id=uuid4(),
            policy_key=policy_key,
            policy_topic=members[0].policy_topic if members else "unassigned",
            candidate_ids=[candidate.id for candidate in members],
            member_count=len(members),
            summary=members[0].summary if members else "",
        )
        await _populate_cluster_artifacts(cluster, candidates_by_id, llm_router, degradations)
        clusters.append(cluster)
    return clusters


async def _populate_cluster_artifacts(
    cluster: ReplayCluster,
    candidates_by_id: dict[UUID, ReplayCandidate],
    llm_router: LLMRouter,
    degradations: list[ReplayDegradationEvent],
) -> None:
    ballot_prompt = BALLOT_PROMPT_TEMPLATE.format(
        policy_key=cluster.policy_key,
        member_count=cluster.member_count,
        submissions_block=_build_ballot_submissions_block(cluster, candidates_by_id),
    )
    ballot_response = await llm_router.complete(
        tier="english_reasoning",
        prompt=ballot_prompt,
        system_prompt=BALLOT_SYSTEM_PROMPT,
        temperature=0.1,
    )
    if ballot_response.primary_model_failed:
        degradations.append(ReplayDegradationEvent(
            step="ballot_generation",
            entity_id=cluster.policy_key,
            event_type="model_fallback",
            detail=f"Primary model failed, used {ballot_response.model}",
            model=ballot_response.model,
            fallback_from=ballot_response.fallback_from,
        ))
    ballot_payload = _parse_ballot_response(ballot_response.text)
    members = [candidates_by_id[candidate_id] for candidate_id in cluster.candidate_ids if candidate_id in candidates_by_id]
    (
        cluster.ballot_question,
        cluster.ballot_question_fa,
        cluster.summary,
        _validation_flags,
    ) = _sanitize_ballot_wording(cluster=cluster, members=members, parsed=ballot_payload)
    if members and any(candidate.ballot_readiness == "needs-refinement" for candidate in members):
        refinement_prompt = REFINEMENT_PROMPT_TEMPLATE.format(
            policy_key=cluster.policy_key,
            policy_topic=cluster.policy_topic,
            summary=cluster.summary,
            submissions_block=_build_refinement_submissions_block(cluster, candidates_by_id),
        )
        refinement_response = await llm_router.complete(
            tier="english_reasoning",
            prompt=refinement_prompt,
            system_prompt=REFINEMENT_SYSTEM_PROMPT,
        )
        if refinement_response.primary_model_failed:
            degradations.append(ReplayDegradationEvent(
                step="refinement",
                entity_id=cluster.policy_key,
                event_type="model_fallback",
                detail=f"Primary model failed, used {refinement_response.model}",
                model=refinement_response.model,
                fallback_from=refinement_response.fallback_from,
            ))
        refinement_payload = _parse_refinement_payload(refinement_response.text)
        (
            cluster.refinement_draft,
            cluster.refinement_draft_fa,
            cluster.refinement_confidence,
            cluster.refinement_requires_clarification,
            cluster.refinement_notes,
            _validation_flags,
        ) = _sanitize_refinement_output(
            cluster=cluster,
            members=members,
            payload=refinement_payload,
        )
        return

    if members and not all(candidate.ballot_readiness == "ballot-ready" for candidate in members):
        return

    try:
        result = await _generate_options_for_cluster(cluster, candidates_by_id, llm_router)
        cluster.options = result.options
        for event in result.debug_events:
            degradations.append(ReplayDegradationEvent(
                step="option_generation",
                entity_id=cluster.policy_key,
                event_type=event.event_type,
                detail=event.detail,
                model=event.model,
                fallback_from=event.fallback_from,
            ))
    except Exception as exc:
        degradations.append(ReplayDegradationEvent(
            step="option_generation",
            entity_id=cluster.policy_key,
            event_type="options_fallback_used",
            detail=f"LLM option generation failed: {type(exc).__name__}: {exc}",
        ))
        cluster.options = _fallback_options(cluster)


def _readiness_counts(cluster: ReplayCluster, candidates: list[ReplayCandidate]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    cluster_ids = set(cluster.candidate_ids)
    for candidate in candidates:
        if candidate.id in cluster_ids:
            counts[candidate.ballot_readiness] += 1
    return dict(sorted(counts.items()))


def serialize_replay_inputs(submissions: list[ReplaySubmissionInput]) -> list[dict[str, Any]]:
    return [asdict(item) for item in submissions]


def replay_metadata(
    *,
    source: str,
    submissions: list[ReplaySubmissionInput],
    router: ReplayCachingLLMRouter | None = None,
) -> dict[str, Any]:
    metadata = {
        "source": source,
        "submission_count": len(submissions),
        "dataset_fingerprint": dataset_fingerprint(submissions),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    if router is not None:
        metadata["router"] = router.stats()
    return metadata
