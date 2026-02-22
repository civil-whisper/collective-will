"""Comprehensive pipeline test: 1050 inputs → canonicalize → embed → cluster → validate.

First run  (GENERATE_PIPELINE_CACHE=1): calls real LLM APIs, saves outputs to cache (~30 min)
Subsequent runs: replays from cache, finishes in seconds.

Usage:
    # Generate cache (one-time, costs ~$2-3):
    GENERATE_PIPELINE_CACHE=1 uv run pytest tests/test_pipeline/test_pipeline_comprehensive.py -s

    # Run from cache (free, fast):
    uv run pytest tests/test_pipeline/test_pipeline_comprehensive.py
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import Settings, get_settings
from src.db.anchoring import DailyAnchor
from src.db.evidence import EvidenceLogEntry, verify_chain
from src.db.queries import create_submission, create_user
from src.models.cluster import Cluster
from src.models.endorsement import PolicyEndorsement
from src.models.submission import PolicyCandidate, Submission, SubmissionCreate
from src.models.user import User, UserCreate
from src.models.vote import VotingCycle
from src.pipeline.llm import EmbeddingResult, LLMResponse, LLMRouter
from src.scheduler import run_pipeline
from tests.fixtures.pipeline_test_data import CLUSTER_IDS, generate_inputs

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent.parent / "fixtures" / "pipeline_cache.json.gz"
GENERATE_MODE = bool(os.getenv("GENERATE_PIPELINE_CACHE"))
SAMPLE_PERCENT = int(os.getenv("PIPELINE_SAMPLE", "100"))
PROJECT_ROOT = Path(__file__).parent.parent.parent

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not GENERATE_MODE and not os.getenv("PIPELINE_SAMPLE"),
        reason="Comprehensive pipeline test: run with PIPELINE_SAMPLE=10 (or GENERATE_PIPELINE_CACHE=1 for full).",
    ),
    pytest.mark.skipif(
        not CACHE_PATH.exists() and not GENERATE_MODE,
        reason="Pipeline cache not found. Run with GENERATE_PIPELINE_CACHE=1 to generate.",
    ),
]


@pytest.fixture(autouse=True)
def _real_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Override the default test env with real .env values for integration testing."""
    from dotenv import dotenv_values

    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        pytest.skip(".env file not found")
    for key, value in dotenv_values(env_file).items():
        if value is not None:
            monkeypatch.setenv(key, value)
    # Lower cluster threshold for smaller samples
    if SAMPLE_PERCENT < 100:
        monkeypatch.setenv("MIN_PREBALLOT_ENDORSEMENTS", "3")


# ---------------------------------------------------------------------------
# Caching LLM Router
# ---------------------------------------------------------------------------

def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _round_vector(v: list[float], decimals: int = 6) -> list[float]:
    return [round(x, decimals) for x in v]


def _load_cache(path: Path) -> dict[str, Any]:
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return {"completions": {}, "embeddings": {}}


def _save_cache(cache: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(cache, f, separators=(",", ":"))
    size_mb = path.stat().st_size / (1024 * 1024)
    logger.info("Cache saved to %s (%.1f MB)", path, size_mb)


class CachingLLMRouter(LLMRouter):
    """LLMRouter that caches completions and embeddings to disk."""

    def __init__(self, cache_path: Path, settings: Settings | None = None) -> None:
        super().__init__(settings=settings)
        self.cache_path = cache_path
        self._cache = _load_cache(cache_path)
        self.cache_hits = 0
        self.cache_misses = 0
        self._completion_count = 0

    async def complete(
        self,
        *,
        tier: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_s: float = 60.0,
    ) -> LLMResponse:
        key = _cache_key(f"{tier}::{prompt}")
        cached = self._cache["completions"].get(key)
        if cached is not None:
            self.cache_hits += 1
            return LLMResponse(**cached)

        self.cache_misses += 1
        self._completion_count += 1
        if self._completion_count % 50 == 0:
            logger.info(
                "  [progress] %d completions done (%d cached, %d live)",
                self._completion_count,
                self.cache_hits,
                self.cache_misses,
            )

        result = await super().complete(
            tier=tier,  # type: ignore[arg-type]
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )
        self._cache["completions"][key] = result.model_dump()
        return result

    async def embed(self, texts: list[str], timeout_s: float = 60.0) -> EmbeddingResult:
        all_cached = True
        vectors: list[list[float]] = []
        for text in texts:
            key = _cache_key(text)
            cached_vec = self._cache["embeddings"].get(key)
            if cached_vec is not None:
                vectors.append(cached_vec)
            else:
                all_cached = False
                break

        if all_cached:
            self.cache_hits += len(texts)
            return EmbeddingResult(vectors=vectors, model="cached", provider="cache")

        self.cache_misses += len(texts)
        result = await super().embed(texts, timeout_s=timeout_s)
        for text, vector in zip(texts, result.vectors, strict=True):
            key = _cache_key(text)
            self._cache["embeddings"][key] = _round_vector(vector)
        return result

    def save(self) -> None:
        _save_cache(self._cache, self.cache_path)

    def stats(self) -> str:
        return f"hits={self.cache_hits}, misses={self.cache_misses}"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

async def _clean_all(session: AsyncSession) -> None:
    models = (DailyAnchor, EvidenceLogEntry, PolicyEndorsement, Cluster, VotingCycle, PolicyCandidate, Submission, User)
    for model in models:
        await session.execute(delete(model))
    await session.commit()


async def _create_eligible_user(session: AsyncSession) -> User:
    user = await create_user(
        session,
        UserCreate(
            email=f"pipeline-comp-{uuid4().hex[:8]}@example.com",
            locale="fa",
            messaging_account_ref=str(uuid4()),
        ),
    )
    user.email_verified = True
    user.messaging_verified = True
    user.messaging_account_age = datetime.now(UTC) - timedelta(hours=72)
    await session.commit()
    return user


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def _sample_inputs(inputs: list[dict[str, str]], percent: int) -> list[dict[str, str]]:
    """Proportionally sample inputs, keeping cluster distribution balanced."""
    import random

    random.seed(42)
    by_cluster: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in inputs:
        by_cluster[item["expected_cluster"]].append(item)

    sampled: list[dict[str, str]] = []
    for _cluster_id, items in by_cluster.items():
        n = max(1, len(items) * percent // 100)
        sampled.extend(random.sample(items, min(n, len(items))))
    return sampled


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

async def test_comprehensive_pipeline() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    router = CachingLLMRouter(cache_path=CACHE_PATH, settings=settings)

    all_inputs = generate_inputs()
    if SAMPLE_PERCENT < 100:
        inputs = _sample_inputs(all_inputs, SAMPLE_PERCENT)
        logger.info("Sampled %d/%d inputs (%d%%)", len(inputs), len(all_inputs), SAMPLE_PERCENT)
    else:
        inputs = all_inputs
    assert len(inputs) >= 10, f"Expected >=10 inputs, got {len(inputs)}"

    try:
        async with maker() as session:
            await _clean_all(session)
            user = await _create_eligible_user(session)

            # --- Submit all inputs ---
            submission_cluster_map: dict[UUID, str] = {}
            for item in inputs:
                sub = await create_submission(
                    session,
                    SubmissionCreate(
                        user_id=user.id,
                        raw_text=item["text"],
                        language=item["language"],
                        hash=hashlib.sha256(item["text"].encode()).hexdigest(),
                    ),
                )
                submission_cluster_map[sub.id] = item["expected_cluster"]
            await session.commit()
            logger.info("Submitted %d inputs", len(inputs))

            # --- Run pipeline ---
            logger.info("Running pipeline (%s mode)...", "GENERATE" if GENERATE_MODE else "CACHED")
            result = await run_pipeline(session=session, llm_router=router)

            # --- Save cache after pipeline completes ---
            router.save()
            logger.info("Router stats: %s", router.stats())

            # --- Basic assertions ---
            assert not result.errors, f"Pipeline errors: {result.errors}"
            assert result.processed_submissions == len(inputs)
            assert result.created_candidates == len(inputs), (
                f"Expected {len(inputs)} candidates, got {result.created_candidates}"
            )

            # --- Verify all candidates have embeddings ---
            candidates = list(
                (await session.execute(select(PolicyCandidate))).scalars().all()
            )
            assert len(candidates) == len(inputs)
            missing_embeddings = [c.id for c in candidates if c.embedding is None or len(c.embedding) == 0]
            assert not missing_embeddings, f"{len(missing_embeddings)} candidates without embeddings"

            # --- Verify clustering produced meaningful groups ---
            clusters = list((await session.execute(select(Cluster))).scalars().all())
            min_expected_clusters = 3 if SAMPLE_PERCENT < 50 else 5
            assert result.created_clusters >= min_expected_clusters, (
                f"Expected >={min_expected_clusters} clusters, got {result.created_clusters}"
            )

            # --- Cluster purity check ---
            candidate_to_sub: dict[UUID, UUID] = {c.id: c.submission_id for c in candidates}
            cluster_purity_scores: list[float] = []
            cluster_theme_map: dict[str, str] = {}

            for cluster in clusters:
                expected_labels = [
                    submission_cluster_map.get(candidate_to_sub.get(cid, uuid4()), "")
                    for cid in cluster.candidate_ids
                ]
                label_counts = Counter(lbl for lbl in expected_labels if lbl)
                if not label_counts:
                    continue
                dominant_label, dominant_count = label_counts.most_common(1)[0]
                purity = dominant_count / len(expected_labels)
                cluster_purity_scores.append(purity)
                cluster_theme_map[str(cluster.id)] = f"{dominant_label} (purity={purity:.0%}, n={len(expected_labels)})"

            avg_purity = sum(cluster_purity_scores) / len(cluster_purity_scores) if cluster_purity_scores else 0
            logger.info(
                "Clusters: %d, avg purity: %.0f%%",
                len(clusters),
                avg_purity * 100,
            )
            for cid, desc in cluster_theme_map.items():
                logger.info("  Cluster %s: %s", cid[:8], desc)

            min_purity = 0.3 if SAMPLE_PERCENT <= 20 else 0.5 if SAMPLE_PERCENT < 50 else 0.6
            assert avg_purity >= min_purity, f"Average cluster purity {avg_purity:.0%} < {min_purity:.0%}"

            # --- Check theme coverage ---
            theme_purity_thresh = 0.3 if SAMPLE_PERCENT <= 20 else 0.4 if SAMPLE_PERCENT < 50 else 0.5
            theme_size_thresh = 3 if SAMPLE_PERCENT <= 20 else 5 if SAMPLE_PERCENT < 50 else 10
            themes_found: set[str] = set()
            for cluster in clusters:
                expected_labels = [
                    submission_cluster_map.get(candidate_to_sub.get(cid, uuid4()), "")
                    for cid in cluster.candidate_ids
                ]
                label_counts = Counter(lbl for lbl in expected_labels if lbl)
                if label_counts:
                    dominant = label_counts.most_common(1)[0][0]
                    purity = label_counts[dominant] / len(expected_labels)
                    if purity >= theme_purity_thresh and len(expected_labels) >= theme_size_thresh:
                        themes_found.add(dominant)

            logger.info(
                "Themes found: %d/%d — %s",
                len(themes_found),
                len(CLUSTER_IDS),
                sorted(themes_found),
            )
            min_themes = 2 if SAMPLE_PERCENT <= 20 else 5 if SAMPLE_PERCENT < 50 else 7
            assert len(themes_found) >= min_themes, (
                f"Expected >={min_themes} themes in clusters, found {len(themes_found)}: {sorted(themes_found)}"
            )

            # --- Evidence chain integrity ---
            valid, entry_count = await verify_chain(session)
            assert valid, "Evidence hash chain is broken"
            assert entry_count >= len(inputs), f"Expected >={len(inputs)} evidence entries, got {entry_count}"

            # --- Voting cycle created ---
            cycles = list((await session.execute(select(VotingCycle))).scalars().all())
            assert len(cycles) >= 1

            logger.info(
                "PASSED: %d inputs → %d candidates → %d clusters (%.0f%% avg purity), "
                "%d evidence entries, chain valid",
                len(inputs),
                len(candidates),
                len(clusters),
                avg_purity * 100,
                entry_count,
            )

    finally:
        router.save()
        await engine.dispose()
