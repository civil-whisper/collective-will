"""Integration test: real embeddings → clustering → validate group quality.

Uses pre-computed embeddings from a fixture file (no LLM calls at test time).
250 policy texts from 10 semantic groups + 50 outliers are embedded once and
cached.  Three test scenarios exercise the clustering algorithm end-to-end.

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
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from numpy.typing import NDArray

from src.models.submission import PolicyCandidate, PolicyDomain
from src.pipeline.cluster import run_clustering
from tests.fixtures.pipeline_test_data import _CLUSTERS, _OUTLIERS

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
    domain: PolicyDomain
    embedding: list[float] | NDArray[Any] | None
    expected_cluster: str


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

DOMAIN_MAP: dict[str, PolicyDomain] = {
    "free_speech": PolicyDomain.RIGHTS,
    "clean_water": PolicyDomain.OTHER,
    "education": PolicyDomain.OTHER,
    "healthcare": PolicyDomain.OTHER,
    "environment": PolicyDomain.OTHER,
    "women_rights": PolicyDomain.RIGHTS,
    "economy": PolicyDomain.ECONOMY,
    "judiciary": PolicyDomain.JUSTICE,
    "housing": PolicyDomain.ECONOMY,
    "anticorruption": PolicyDomain.GOVERNANCE,
}


def _build_test_inputs() -> list[dict[str, str]]:
    """Build ~250 test inputs: 200 in-cluster (base texts) + 50 outliers."""
    inputs: list[dict[str, str]] = []
    for cluster in _CLUSTERS:
        cluster_id = str(cluster["id"])
        for text in cluster["fa"]:  # type: ignore[union-attr]
            inputs.append({
                "text": str(text),
                "language": "fa",
                "expected_cluster": cluster_id,
            })
        for text in cluster["en"]:  # type: ignore[union-attr]
            inputs.append({
                "text": str(text),
                "language": "en",
                "expected_cluster": cluster_id,
            })
    for outlier in _OUTLIERS:
        inputs.append({
            "text": outlier["text"],
            "language": outlier["lang"],
            "expected_cluster": "",
        })
    return inputs


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
                domain=DOMAIN_MAP.get(cluster_id, PolicyDomain.OTHER),
                embedding=vec,
                expected_cluster=cluster_id,
            )
        )
    return candidates


def _cluster_purity(
    clusters: list[Any],
    id_to_expected: dict[UUID, str],
) -> tuple[float, dict[str, str]]:
    """Return (avg_purity, {cluster_summary: dominant_label})."""
    purity_scores: list[float] = []
    theme_map: dict[str, str] = {}
    for cluster in clusters:
        labels = [id_to_expected.get(cid, "") for cid in cluster.candidate_ids]
        label_counts = Counter(lbl for lbl in labels if lbl)
        if not label_counts:
            continue
        dominant, count = label_counts.most_common(1)[0]
        purity = count / len(labels)
        purity_scores.append(purity)
        theme_map[cluster.summary] = f"{dominant} (purity={purity:.0%}, n={len(labels)})"
    avg = sum(purity_scores) / len(purity_scores) if purity_scores else 0.0
    return avg, theme_map


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


class TestAllInputs:
    """Scenario 1: feed all 250 texts → expect ~10 clusters with high purity."""

    def test_forms_expected_number_of_clusters(self) -> None:
        inputs, embeddings = _load_all()
        candidates = _make_candidates(inputs, embeddings)
        assert len(candidates) >= 200

        result = run_clustering(
            candidates=cast(list[PolicyCandidate], candidates),
            cycle_id=uuid4(),
            min_cluster_size=5,
        )
        assert result.clusters, "No clusters formed"
        assert len(result.clusters) >= 7, (
            f"Expected >=7 clusters from 10 themes, got {len(result.clusters)}"
        )

    def test_cluster_purity_is_high(self) -> None:
        inputs, embeddings = _load_all()
        candidates = _make_candidates(inputs, embeddings)
        id_to_expected = {c.id: c.expected_cluster for c in candidates}

        result = run_clustering(
            candidates=cast(list[PolicyCandidate], candidates),
            cycle_id=uuid4(),
            min_cluster_size=5,
        )
        avg_purity, theme_map = _cluster_purity(result.clusters, id_to_expected)

        for summary, desc in theme_map.items():
            print(f"  {summary}: {desc}")
        print(f"  Average purity: {avg_purity:.0%}")

        assert avg_purity >= 0.60, (
            f"Average cluster purity {avg_purity:.0%} < 60%"
        )

    def test_theme_coverage(self) -> None:
        """Most of the 10 themes should appear as a dominant label in some cluster."""
        inputs, embeddings = _load_all()
        candidates = _make_candidates(inputs, embeddings)
        id_to_expected = {c.id: c.expected_cluster for c in candidates}

        result = run_clustering(
            candidates=cast(list[PolicyCandidate], candidates),
            cycle_id=uuid4(),
            min_cluster_size=5,
        )
        themes_found: set[str] = set()
        for cluster in result.clusters:
            labels = [id_to_expected.get(cid, "") for cid in cluster.candidate_ids]
            label_counts = Counter(lbl for lbl in labels if lbl)
            if label_counts:
                dominant, count = label_counts.most_common(1)[0]
                if count / len(labels) >= 0.5 and len(labels) >= 5:
                    themes_found.add(dominant)

        print(f"  Themes found: {len(themes_found)}/10 — {sorted(themes_found)}")
        assert len(themes_found) >= 6, (
            f"Expected >=6 themes in pure clusters, found {len(themes_found)}"
        )

    def test_candidate_conservation(self) -> None:
        inputs, embeddings = _load_all()
        candidates = _make_candidates(inputs, embeddings)

        result = run_clustering(
            candidates=cast(list[PolicyCandidate], candidates),
            cycle_id=uuid4(),
            min_cluster_size=5,
        )
        clustered: set[UUID] = set()
        for c in result.clusters:
            overlap = clustered & set(c.candidate_ids)
            assert not overlap
            clustered.update(c.candidate_ids)

        noise = set(result.noise_candidate_ids)
        assert not (clustered & noise)
        all_ids = {c.id for c in candidates}
        assert clustered | noise == all_ids


class TestOnePerGroup:
    """Scenario 2: one text from each group (10 total) → too few for clusters."""

    def test_no_clusters_formed(self) -> None:
        inputs, embeddings = _load_all()
        cluster_ids = [str(c["id"]) for c in _CLUSTERS]

        selected: list[dict[str, str]] = []
        for cid in cluster_ids:
            match = next(
                (i for i in inputs if i["expected_cluster"] == cid),
                None,
            )
            if match:
                selected.append(match)

        candidates = _make_candidates(selected, embeddings)
        assert len(candidates) == 10

        result = run_clustering(
            candidates=cast(list[PolicyCandidate], candidates),
            cycle_id=uuid4(),
            min_cluster_size=5,
        )
        assert len(result.clusters) == 0, (
            f"Expected 0 clusters from 10 singletons, got {len(result.clusters)}"
        )
        assert len(result.noise_candidate_ids) == 10


class TestSingleGroup:
    """Scenario 3: all texts from one cluster + outlier background → group forms."""

    def test_single_group_clusters_together(self) -> None:
        inputs, embeddings = _load_all()
        target_cluster = "women_rights"

        group_inputs = [i for i in inputs if i["expected_cluster"] == target_cluster]
        outlier_inputs = [i for i in inputs if i["expected_cluster"] == ""]
        random.seed(42)
        some_outliers = random.sample(outlier_inputs, min(15, len(outlier_inputs)))

        candidates = _make_candidates(group_inputs + some_outliers, embeddings)
        group_ids = {
            c.id for c in candidates if c.expected_cluster == target_cluster
        }
        assert len(group_ids) >= 15

        result = run_clustering(
            candidates=cast(list[PolicyCandidate], candidates),
            cycle_id=uuid4(),
            min_cluster_size=5,
        )
        assert result.clusters, (
            f"Expected at least 1 cluster from {len(group_ids)} "
            f"'{target_cluster}' texts, got all noise"
        )

        biggest = max(result.clusters, key=lambda c: c.member_count)
        overlap = group_ids & set(biggest.candidate_ids)
        recall = len(overlap) / len(group_ids)
        precision = len(overlap) / biggest.member_count
        print(
            f"  Biggest cluster: {biggest.member_count} members, "
            f"recall={recall:.0%}, precision={precision:.0%}"
        )
        assert recall >= 0.5, f"Recall {recall:.0%} < 50%"
        assert precision >= 0.7, f"Precision {precision:.0%} < 70%"

    def test_healthcare_too_diverse_to_cluster_alone(self) -> None:
        """Healthcare spans many sub-topics — without other groups for
        density contrast, HDBSCAN treats them as noise. This is expected
        and documents the algorithm's behavior."""
        inputs, embeddings = _load_all()
        healthcare = [i for i in inputs if i["expected_cluster"] == "healthcare"]
        candidates = _make_candidates(healthcare, embeddings)
        assert len(candidates) == 20

        result = run_clustering(
            candidates=cast(list[PolicyCandidate], candidates),
            cycle_id=uuid4(),
            min_cluster_size=5,
        )
        assert len(result.clusters) == 0, (
            "Healthcare texts are too semantically diverse to form "
            "a single cluster without density contrast from other groups"
        )
        assert len(result.noise_candidate_ids) == 20
