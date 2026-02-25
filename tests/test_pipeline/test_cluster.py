from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray

from src.models.submission import PolicyCandidate, PolicyDomain
from src.pipeline.cluster import run_clustering, variance_check


@dataclass
class FakeCandidate:
    id: UUID
    domain: PolicyDomain
    embedding: list[float] | NDArray[Any] | None


def _make_tight_group(n: int, center: list[float], spread: float = 0.01) -> list[FakeCandidate]:
    return [
        FakeCandidate(
            id=uuid4(),
            domain=PolicyDomain.ECONOMY,
            embedding=[c + np.random.uniform(-spread, spread) for c in center],
        )
        for _ in range(n)
    ]


def test_numpy_array_embeddings_do_not_raise() -> None:
    """pgvector returns numpy arrays, not Python lists — verify no truth-value error."""
    candidates = cast(
        list[PolicyCandidate],
        [
            FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=np.array([float(i), 0.0]))
            for i in range(10)
        ],
    )
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5)
    total = sum(c.member_count for c in result.clusters) + len(result.noise_candidate_ids)
    assert total == len(candidates)


def test_too_few_candidates_returns_empty() -> None:
    candidates = cast(
        list[PolicyCandidate],
        [FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[0.0, 0.0])],
    )
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5)
    assert len(result.clusters) == 0
    assert len(result.noise_candidate_ids) == 1


def test_clustering_forms_clusters() -> None:
    np.random.seed(42)
    group_a = _make_tight_group(10, [0.0, 0.0], spread=0.01)
    group_b = _make_tight_group(10, [10.0, 10.0], spread=0.01)
    candidates = cast(list[PolicyCandidate], group_a + group_b)
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5)
    assert len(result.clusters) >= 2


def test_min_cluster_size_respected() -> None:
    np.random.seed(42)
    group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
    candidates = cast(list[PolicyCandidate], group)
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=4)
    for cluster in result.clusters:
        assert cluster.member_count >= 4


def test_noise_points() -> None:
    np.random.seed(42)
    group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
    outlier = FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[100.0, 100.0])
    candidates = cast(list[PolicyCandidate], group + [outlier])
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5)
    total = sum(c.member_count for c in result.clusters) + len(result.noise_candidate_ids)
    assert total == len(candidates)


def test_determinism_same_seed_same_result() -> None:
    np.random.seed(42)
    group_a = _make_tight_group(10, [0.0, 0.0], spread=0.01)
    group_b = _make_tight_group(10, [10.0, 10.0], spread=0.01)
    candidates = cast(list[PolicyCandidate], group_a + group_b)

    r1 = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5, random_seed=42)
    r2 = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5, random_seed=42)
    assert len(r1.clusters) == len(r2.clusters)
    for c1, c2 in zip(r1.clusters, r2.clusters, strict=True):
        assert set(c1.candidate_ids) == set(c2.candidate_ids)


def test_cluster_has_run_id_and_params() -> None:
    np.random.seed(42)
    group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
    candidates = cast(list[PolicyCandidate], group)
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5, random_seed=99)
    assert result.run_id
    assert result.random_seed == 99
    assert result.clustering_params["min_cluster_size"] == 5
    for cluster in result.clusters:
        assert cluster.run_id == result.run_id
        assert cluster.random_seed == 99


def test_centroid_is_mean_of_members() -> None:
    c1 = FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=[0.0, 0.0])
    c2 = FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=[2.0, 2.0])
    candidates = cast(list[PolicyCandidate], [c1, c2] * 5)
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=2)
    for cluster in result.clusters:
        if cluster.centroid_embedding:
            assert len(cluster.centroid_embedding) == 2


def test_member_count_matches_candidate_ids() -> None:
    np.random.seed(42)
    group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
    candidates = cast(list[PolicyCandidate], group)
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5)
    for cluster in result.clusters:
        assert cluster.member_count == len(cluster.candidate_ids)


# --- Variance check ---
def test_variance_check_small_dataset_skip() -> None:
    candidates = cast(
        list[PolicyCandidate],
        [FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[0.0, 0.0])],
    )
    flags = variance_check(candidates=candidates, cycle_id=uuid4())
    assert all(f is False for f in flags)


def test_variance_check_runs_multiple_times() -> None:
    np.random.seed(42)
    group_a = _make_tight_group(15, [0.0, 0.0], spread=0.01)
    group_b = _make_tight_group(15, [10.0, 10.0], spread=0.01)
    candidates = cast(list[PolicyCandidate], group_a + group_b)
    flags = variance_check(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5)
    assert len(flags) == len(candidates)
