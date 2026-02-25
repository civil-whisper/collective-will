from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray

from src.models.submission import PolicyCandidate, PolicyDomain
from src.pipeline.cluster import ClusterRunResult, run_clustering, variance_check


@dataclass
class FakeCandidate:
    id: UUID
    domain: PolicyDomain
    embedding: list[float] | NDArray[Any] | None


def _make_tight_group(
    n: int,
    center: list[float],
    spread: float = 0.01,
    domain: PolicyDomain = PolicyDomain.ECONOMY,
) -> list[FakeCandidate]:
    return [
        FakeCandidate(
            id=uuid4(),
            domain=domain,
            embedding=[c + np.random.uniform(-spread, spread) for c in center],
        )
        for _ in range(n)
    ]


def _ids(candidates: list[FakeCandidate]) -> set[UUID]:
    return {c.id for c in candidates}


def _cluster(candidates: list[FakeCandidate], **kwargs: Any) -> ClusterRunResult:
    return run_clustering(
        candidates=cast(list[PolicyCandidate], candidates),
        cycle_id=kwargs.pop("cycle_id", uuid4()),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Edge cases: empty, small, and None-embedding inputs
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_candidates(self) -> None:
        result = _cluster([])
        assert result.clusters == []
        assert result.noise_candidate_ids == []

    def test_single_candidate_below_min_cluster_size(self) -> None:
        c = FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[0.0, 0.0])
        result = _cluster([c], min_cluster_size=5)
        assert len(result.clusters) == 0
        assert result.noise_candidate_ids == [c.id]

    def test_none_embeddings_filtered_out(self) -> None:
        valid = FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=[1.0, 2.0])
        no_embedding = FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=None)
        result = _cluster([valid, no_embedding], min_cluster_size=5)
        assert len(result.clusters) == 0
        assert valid.id in result.noise_candidate_ids
        assert no_embedding.id not in result.noise_candidate_ids

    def test_all_none_embeddings_returns_empty(self) -> None:
        candidates = [
            FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=None)
            for _ in range(5)
        ]
        result = _cluster(candidates, min_cluster_size=2)
        assert result.clusters == []
        assert result.noise_candidate_ids == []

    def test_mixed_none_and_valid_embeddings(self) -> None:
        np.random.seed(42)
        valid_group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        none_candidates = [
            FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=None)
            for _ in range(3)
        ]
        result = _cluster(valid_group + none_candidates, min_cluster_size=5)
        all_referenced = set(result.noise_candidate_ids)
        for c in result.clusters:
            all_referenced.update(c.candidate_ids)
        assert all_referenced == _ids(valid_group)
        for nc in none_candidates:
            assert nc.id not in all_referenced


# ---------------------------------------------------------------------------
# Numpy array embeddings (pgvector returns numpy, not Python lists)
# ---------------------------------------------------------------------------


class TestNumpyArrays:
    def test_numpy_embeddings_do_not_raise(self) -> None:
        """pgvector returns numpy arrays — verify no truth-value error."""
        candidates = [
            FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=np.array([float(i), 0.0]))
            for i in range(10)
        ]
        result = _cluster(candidates, min_cluster_size=5)
        total = sum(c.member_count for c in result.clusters) + len(result.noise_candidate_ids)
        assert total == len(candidates)

    def test_numpy_embeddings_form_correct_clusters(self) -> None:
        """Numpy arrays should produce the same clusters as Python lists."""
        np.random.seed(42)
        center_a, center_b = [0.0, 0.0], [100.0, 100.0]
        def _np_group(n: int, center: list[float], domain: PolicyDomain) -> list[FakeCandidate]:
            return [
                FakeCandidate(
                    id=uuid4(),
                    domain=domain,
                    embedding=np.array([c + np.random.uniform(-0.01, 0.01) for c in center]),
                )
                for _ in range(n)
            ]

        group_a_np = _np_group(8, center_a, PolicyDomain.ECONOMY)
        group_b_np = _np_group(8, center_b, PolicyDomain.RIGHTS)
        result = _cluster(group_a_np + group_b_np, min_cluster_size=5)
        assert len(result.clusters) >= 2

        cluster_id_sets = [set(c.candidate_ids) for c in result.clusters]
        for group in [group_a_np, group_b_np]:
            group_ids = _ids(group)
            assert any(group_ids <= cs for cs in cluster_id_sets), (
                f"Group not found as subset of any cluster: {group_ids}"
            )


# ---------------------------------------------------------------------------
# Core clustering behavior
# ---------------------------------------------------------------------------


class TestClusterFormation:
    def test_two_distinct_groups(self) -> None:
        np.random.seed(42)
        group_a = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        group_b = _make_tight_group(10, [10.0, 10.0], spread=0.01)
        result = _cluster(group_a + group_b, min_cluster_size=5)
        assert len(result.clusters) >= 2

    def test_uniform_group_is_all_noise(self) -> None:
        """HDBSCAN needs density contrast — a single uniform group is classified as noise."""
        np.random.seed(42)
        group = _make_tight_group(10, [5.0, 5.0], spread=0.01)
        result = _cluster(group, min_cluster_size=5)
        assert len(result.clusters) == 0
        assert set(result.noise_candidate_ids) == _ids(group)

    def test_min_cluster_size_respected(self) -> None:
        np.random.seed(42)
        group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        result = _cluster(group, min_cluster_size=4)
        for cluster in result.clusters:
            assert cluster.member_count >= 4

    def test_candidate_conservation(self) -> None:
        """Every embedded candidate must end up in exactly one cluster or as noise."""
        np.random.seed(42)
        group_a = _make_tight_group(10, [0.0, 0.0])
        group_b = _make_tight_group(10, [50.0, 50.0])
        outlier = FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[999.0, 999.0])
        all_candidates = group_a + group_b + [outlier]
        result = _cluster(all_candidates, min_cluster_size=5)

        clustered_ids: set[UUID] = set()
        for c in result.clusters:
            overlap = clustered_ids & set(c.candidate_ids)
            assert not overlap, f"Candidate in multiple clusters: {overlap}"
            clustered_ids.update(c.candidate_ids)

        noise_set = set(result.noise_candidate_ids)
        assert not (clustered_ids & noise_set), "Candidate in both cluster and noise"
        assert clustered_ids | noise_set == _ids(all_candidates)

    def test_noise_points_separated(self) -> None:
        np.random.seed(42)
        group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        outlier = FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[100.0, 100.0])
        result = _cluster(group + [outlier], min_cluster_size=5)
        assert outlier.id in result.noise_candidate_ids

    def test_all_noise_when_widely_spread(self) -> None:
        candidates = [
            FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[float(i) * 1000, 0.0])
            for i in range(6)
        ]
        result = _cluster(candidates, min_cluster_size=5)
        assert len(result.clusters) == 0
        assert set(result.noise_candidate_ids) == _ids(candidates)


# ---------------------------------------------------------------------------
# Correctness of cluster metadata (centroid, cohesion, domain, cycle_id)
# ---------------------------------------------------------------------------


class TestClusterMetadata:
    def test_centroid_is_mean_of_members(self) -> None:
        embeddings = [[0.0, 0.0], [4.0, 0.0], [0.0, 4.0], [4.0, 4.0]]
        candidates = [
            FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=e)
            for e in embeddings
        ] * 3  # 12 total so HDBSCAN can form a cluster
        result = _cluster(candidates, min_cluster_size=2)
        for cluster in result.clusters:
            member_embeddings = []
            id_to_emb = {c.id: c.embedding for c in candidates}
            for cid in cluster.candidate_ids:
                member_embeddings.append(id_to_emb[cid])
            expected_centroid = np.mean(member_embeddings, axis=0).tolist()
            assert cluster.centroid_embedding is not None
            for actual, expected in zip(cluster.centroid_embedding, expected_centroid, strict=True):
                assert abs(actual - expected) < 1e-6

    def test_cohesion_in_valid_range(self) -> None:
        np.random.seed(42)
        group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        result = _cluster(group, min_cluster_size=5)
        for cluster in result.clusters:
            assert 0.0 <= cluster.cohesion_score <= 1.0

    def test_tight_cluster_has_high_cohesion(self) -> None:
        """Tight groups have cohesion close to 1.0 (near-zero mean distance)."""
        np.random.seed(42)
        group_a = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        group_b = _make_tight_group(10, [10.0, 10.0], spread=0.01)
        result = _cluster(group_a + group_b, min_cluster_size=5)
        assert len(result.clusters) >= 2
        for cluster in result.clusters:
            assert cluster.cohesion_score > 0.9

    def test_domain_majority_assignment(self) -> None:
        """Cluster domain should be the majority domain of its members."""
        np.random.seed(42)
        econ = _make_tight_group(8, [0.0, 0.0], spread=0.01, domain=PolicyDomain.ECONOMY)
        rights = _make_tight_group(2, [0.0, 0.0], spread=0.01, domain=PolicyDomain.RIGHTS)
        other = _make_tight_group(10, [10.0, 10.0], spread=0.01, domain=PolicyDomain.OTHER)
        result = _cluster(econ + rights + other, min_cluster_size=5)
        assert len(result.clusters) >= 2
        for cluster in result.clusters:
            member_ids = set(cluster.candidate_ids)
            if member_ids & _ids(econ):
                assert cluster.domain == PolicyDomain.ECONOMY
            elif member_ids & _ids(other):
                assert cluster.domain == PolicyDomain.OTHER

    def test_cycle_id_propagated(self) -> None:
        np.random.seed(42)
        group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        cycle_id = uuid4()
        result = _cluster(group, cycle_id=cycle_id, min_cluster_size=5)
        for cluster in result.clusters:
            assert cluster.cycle_id == cycle_id

    def test_member_count_matches_candidate_ids(self) -> None:
        np.random.seed(42)
        group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        result = _cluster(group, min_cluster_size=5)
        for cluster in result.clusters:
            assert cluster.member_count == len(cluster.candidate_ids)


# ---------------------------------------------------------------------------
# Determinism and run metadata
# ---------------------------------------------------------------------------


class TestDeterminismAndMetadata:
    def test_same_seed_same_result(self) -> None:
        np.random.seed(42)
        group_a = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        group_b = _make_tight_group(10, [10.0, 10.0], spread=0.01)
        candidates = group_a + group_b

        r1 = _cluster(candidates, min_cluster_size=5, random_seed=42)
        r2 = _cluster(candidates, min_cluster_size=5, random_seed=42)
        assert len(r1.clusters) == len(r2.clusters)
        for c1, c2 in zip(r1.clusters, r2.clusters, strict=True):
            assert set(c1.candidate_ids) == set(c2.candidate_ids)

    def test_run_id_unique_per_call(self) -> None:
        np.random.seed(42)
        group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        r1 = _cluster(group, min_cluster_size=5)
        r2 = _cluster(group, min_cluster_size=5)
        assert r1.run_id != r2.run_id

    def test_cluster_carries_run_id_and_params(self) -> None:
        np.random.seed(42)
        group = _make_tight_group(10, [0.0, 0.0], spread=0.01)
        result = _cluster(group, min_cluster_size=5, min_samples=2, random_seed=99)
        assert result.run_id
        assert result.random_seed == 99
        assert result.clustering_params == {"min_cluster_size": 5, "min_samples": 2}
        for cluster in result.clusters:
            assert cluster.run_id == result.run_id
            assert cluster.random_seed == 99
            assert cluster.clustering_params == {"min_cluster_size": 5, "min_samples": 2}


# ---------------------------------------------------------------------------
# Higher-dimensional embeddings (realistic production scenario)
# ---------------------------------------------------------------------------


class TestHigherDimensions:
    def test_clustering_with_768d_embeddings(self) -> None:
        """Simulate realistic text-embedding dimensions."""
        rng = np.random.default_rng(42)
        dim = 768
        center_a = rng.standard_normal(dim)
        center_b = center_a + 10.0  # well-separated

        group_a = [
            FakeCandidate(
                id=uuid4(), domain=PolicyDomain.ECONOMY,
                embedding=(center_a + rng.normal(0, 0.01, dim)).tolist(),
            )
            for _ in range(8)
        ]
        group_b = [
            FakeCandidate(
                id=uuid4(), domain=PolicyDomain.RIGHTS,
                embedding=(center_b + rng.normal(0, 0.01, dim)).tolist(),
            )
            for _ in range(8)
        ]
        result = _cluster(group_a + group_b, min_cluster_size=5)
        assert len(result.clusters) >= 2
        total = sum(c.member_count for c in result.clusters) + len(result.noise_candidate_ids)
        assert total == 16

    def test_numpy_768d_embeddings(self) -> None:
        """pgvector returns numpy arrays with real embedding dimensions."""
        rng = np.random.default_rng(42)
        dim = 768
        center = rng.standard_normal(dim)
        candidates = [
            FakeCandidate(
                id=uuid4(),
                domain=PolicyDomain.GOVERNANCE,
                embedding=np.array(center + rng.normal(0, 0.01, dim)),
            )
            for _ in range(10)
        ]
        result = _cluster(candidates, min_cluster_size=5)
        total = sum(c.member_count for c in result.clusters) + len(result.noise_candidate_ids)
        assert total == 10
        for cluster in result.clusters:
            assert cluster.centroid_embedding is not None
            assert len(cluster.centroid_embedding) == dim


# ---------------------------------------------------------------------------
# Variance check
# ---------------------------------------------------------------------------


class TestVarianceCheck:
    def test_small_dataset_skip(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[0.0, 0.0])],
        )
        flags = variance_check(candidates=candidates, cycle_id=uuid4())
        assert all(f is False for f in flags)

    def test_runs_multiple_seeds(self) -> None:
        np.random.seed(42)
        group_a = _make_tight_group(15, [0.0, 0.0], spread=0.01)
        group_b = _make_tight_group(15, [10.0, 10.0], spread=0.01)
        candidates = cast(list[PolicyCandidate], group_a + group_b)
        flags = variance_check(candidates=candidates, cycle_id=uuid4(), min_cluster_size=5)
        assert len(flags) == len(candidates)

    def test_stable_clustering_returns_false(self) -> None:
        np.random.seed(42)
        group_a = _make_tight_group(15, [0.0, 0.0], spread=0.001)
        group_b = _make_tight_group(15, [100.0, 100.0], spread=0.001)
        candidates = cast(list[PolicyCandidate], group_a + group_b)
        flags = variance_check(
            candidates=candidates,
            cycle_id=uuid4(),
            min_cluster_size=5,
            stability_threshold=0.5,
        )
        assert all(f is False for f in flags)
