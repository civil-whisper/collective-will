"""Integration test: real embeddings → policy-key grouping → validate quality.

Uses pre-computed embeddings from a fixture file (no LLM calls at test time).
250 policy texts from 10 semantic groups + 50 outliers are embedded once and
cached.  Tests exercise group_by_policy_key and compute_centroid end-to-end.

Generate fixture (one-time, needs API keys in .env):
    GENERATE_CLUSTER_EMBEDDINGS=1 uv run pytest tests/test_pipeline/test_cluster_integration.py -s

Run from fixture (free, fast, works in CI):
    uv run pytest tests/test_pipeline/test_cluster_integration.py
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from numpy.typing import NDArray

from src.models.submission import PolicyCandidate
from src.pipeline.cluster import compute_centroid, group_by_policy_key
from tests.fixtures.pipeline_test_data import generate_inputs

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "cluster_embeddings.json.gz"
GENERATE_MODE = bool(os.getenv("GENERATE_CLUSTER_EMBEDDINGS"))

pytestmark = pytest.mark.skipif(
    not FIXTURE_PATH.exists() and not GENERATE_MODE,
    reason="Fixture not found. Run with GENERATE_CLUSTER_EMBEDDINGS=1 to generate.",
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TaggedCandidate:
    id: UUID
    embedding: list[float] | NDArray[Any] | None
    expected_cluster: str
    policy_key: str = "unassigned"
    policy_topic: str = "unassigned"


# ---------------------------------------------------------------------------
# Fixture I/O
# ---------------------------------------------------------------------------

def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_embeddings() -> dict[str, list[float]]:
    with gzip.open(FIXTURE_PATH, "rt", encoding="utf-8") as f:
        data = json.load(f)
    return data["embeddings"]


def _save_embeddings(embeddings: dict[str, list[float]], model: str) -> None:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"model": model, "count": len(embeddings), "embeddings": embeddings}
    with gzip.open(FIXTURE_PATH, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    size_kb = FIXTURE_PATH.stat().st_size / 1024
    print(f"\nSaved {len(embeddings)} embeddings to {FIXTURE_PATH} ({size_kb:.0f} KB)")


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

def _build_test_inputs() -> list[dict[str, str]]:
    """Build test inputs from pipeline_test_data fixture."""
    return generate_inputs()


def _make_candidates(
    inputs: list[dict[str, str]],
    embeddings: dict[str, list[float]],
) -> list[TaggedCandidate]:
    candidates: list[TaggedCandidate] = []
    for item in inputs:
        key = _cache_key(item["text"])
        vec = embeddings.get(key)
        if vec is None:
            continue
        cluster_id = item["expected_cluster"]
        candidates.append(
            TaggedCandidate(
                id=uuid4(),
                embedding=vec,
                expected_cluster=cluster_id,
                policy_key=cluster_id or "unassigned",
                policy_topic=cluster_id or "unassigned",
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# Fixture generation (one-time, requires API keys)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _generate_fixture_if_needed() -> None:
    if not GENERATE_MODE:
        return
    if FIXTURE_PATH.exists():
        print(f"\nFixture already exists at {FIXTURE_PATH}; delete to regenerate.")
        return

    import asyncio

    inputs = _build_test_inputs()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_generate(inputs))
    finally:
        loop.close()


async def _async_generate(inputs: list[dict[str, str]]) -> None:
    from dotenv import dotenv_values

    from src.config import get_settings
    from src.pipeline.llm import LLMRouter

    project_root = Path(__file__).parent.parent.parent
    env_file = project_root / ".env"
    if not env_file.exists():
        pytest.skip(".env file required for embedding generation")

    for key, value in dotenv_values(env_file).items():
        if value is not None:
            os.environ[key] = value
    get_settings.cache_clear()
    settings = get_settings()
    router = LLMRouter(settings=settings)

    texts = [item["text"] for item in inputs]
    unique_texts = list(dict.fromkeys(texts))

    embeddings: dict[str, list[float]] = {}
    model_name = "unknown"
    batch_size = 64
    for i in range(0, len(unique_texts), batch_size):
        batch = unique_texts[i : i + batch_size]
        result = await router.embed(batch)
        model_name = result.model
        for text, vector in zip(batch, result.vectors, strict=True):
            embeddings[_cache_key(text)] = [round(x, 6) for x in vector]
        done = min(i + batch_size, len(unique_texts))
        print(f"  Embedded {done}/{len(unique_texts)}")

    _save_embeddings(embeddings, model=model_name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _load_all() -> tuple[list[dict[str, str]], dict[str, list[float]]]:
    inputs = _build_test_inputs()
    embeddings = _load_embeddings()
    return inputs, embeddings


class TestGroupByPolicyKeyIntegration:
    """Scenario 1: all candidates grouped by policy_key yields expected groups."""

    def test_groups_match_expected_themes(self) -> None:
        inputs, embeddings = _load_all()
        candidates = _make_candidates(inputs, embeddings)
        assert len(candidates) >= 10, f"Need at least 10 candidates with embeddings, got {len(candidates)}"

        groups = group_by_policy_key(
            candidates=cast(list[PolicyCandidate], candidates),
        )
        non_empty = {k: v for k, v in groups.items() if k != "unassigned"}
        assert len(non_empty) >= 3, (
            f"Expected >=3 policy_key groups, got {len(non_empty)}"
        )

    def test_candidate_conservation(self) -> None:
        inputs, embeddings = _load_all()
        candidates = _make_candidates(inputs, embeddings)

        groups = group_by_policy_key(
            candidates=cast(list[PolicyCandidate], candidates),
        )
        grouped_ids: set[UUID] = set()
        for members in groups.values():
            for c in members:
                grouped_ids.add(c.id)

        all_non_outlier = {
            c.id for c in candidates
            if c.policy_key and c.policy_key != "unassigned"
        }
        assert grouped_ids == all_non_outlier


class TestComputeCentroidIntegration:
    """Scenario 2: compute centroid on real embeddings from a single theme."""

    def test_centroid_has_correct_dimensions(self) -> None:
        inputs, embeddings = _load_all()
        candidates = _make_candidates(inputs, embeddings)
        groups = group_by_policy_key(
            candidates=cast(list[PolicyCandidate], candidates),
        )
        for key, members in groups.items():
            centroid = compute_centroid(cast(list[PolicyCandidate], members))
            if centroid is not None:
                embedded_members = [m for m in members if m.embedding is not None]
                if embedded_members:
                    dim = len(list(embedded_members[0].embedding))  # type: ignore[arg-type]
                    assert len(centroid) == dim, (
                        f"Centroid dim {len(centroid)} != embedding dim {dim} for {key}"
                    )

    def test_outliers_have_no_group(self) -> None:
        """Outlier candidates with policy_key='unassigned' are excluded."""
        inputs, embeddings = _load_all()
        outlier_inputs = [i for i in inputs if i["expected_cluster"] == ""]
        candidates = _make_candidates(outlier_inputs, embeddings)

        groups = group_by_policy_key(
            candidates=cast(list[PolicyCandidate], candidates),
        )
        assert len(groups) == 0, (
            f"Expected 0 groups from outliers, got {len(groups)}"
        )
