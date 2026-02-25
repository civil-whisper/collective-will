from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate, PolicyDomain
from src.pipeline.agenda import build_agenda
from src.pipeline.cluster import group_by_policy_key, run_clustering, variance_check


@dataclass
class FakeCandidate:
    id: UUID
    domain: PolicyDomain
    embedding: list[float]
    policy_key: str = "test-policy"
    policy_topic: str = "test-topic"


@dataclass
class FakeCluster:
    id: UUID
    member_count: int
    policy_key: str = "test-policy"


def test_clustering_forms_clusters_and_noise() -> None:
    candidates = cast(
        list[PolicyCandidate],
        [
            FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=[0.0, 0.0]),
            FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=[0.0, 0.1]),
            FakeCandidate(id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=[0.1, 0.0]),
            FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[10.0, 10.0]),
            FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[10.1, 10.0]),
        ],
    )
    result = run_clustering(candidates=candidates, cycle_id=uuid4(), min_cluster_size=2)
    clustered_count = sum(len(c.candidate_ids) for c in result.clusters)
    assert clustered_count + len(result.noise_candidate_ids) == len(candidates)
    assert isinstance(result.noise_candidate_ids, list)


def test_variance_check_small_dataset_skip() -> None:
    candidates = cast(
        list[PolicyCandidate],
        [FakeCandidate(id=uuid4(), domain=PolicyDomain.OTHER, embedding=[0.0, 0.0])],
    )
    flags = variance_check(candidates=candidates, cycle_id=uuid4())
    assert flags == [False]


def test_agenda_threshold_gating() -> None:
    cluster_id = uuid4()
    clusters = cast(list[Cluster], [FakeCluster(id=cluster_id, member_count=5)])
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={str(cluster_id): 5},
        min_support=5,
    )
    assert items[0].qualifies is True


def test_group_by_policy_key() -> None:
    candidates = cast(
        list[PolicyCandidate],
        [
            FakeCandidate(
                id=uuid4(), domain=PolicyDomain.ECONOMY,
                embedding=[0.0], policy_key="healthcare-access",
            ),
            FakeCandidate(
                id=uuid4(), domain=PolicyDomain.ECONOMY,
                embedding=[0.0], policy_key="healthcare-access",
            ),
            FakeCandidate(
                id=uuid4(), domain=PolicyDomain.RIGHTS,
                embedding=[0.0], policy_key="internet-censorship",
            ),
        ],
    )
    groups = group_by_policy_key(candidates=candidates)
    assert len(groups) == 2
    assert len(groups["healthcare-access"]) == 2
    assert len(groups["internet-censorship"]) == 1


def test_group_by_policy_key_skips_unassigned() -> None:
    candidates = cast(
        list[PolicyCandidate],
        [
            FakeCandidate(
                id=uuid4(), domain=PolicyDomain.OTHER,
                embedding=[0.0], policy_key="unassigned",
            ),
            FakeCandidate(
                id=uuid4(), domain=PolicyDomain.ECONOMY,
                embedding=[0.0], policy_key="real-policy",
            ),
        ],
    )
    groups = group_by_policy_key(candidates=candidates)
    assert len(groups) == 1
    assert "unassigned" not in groups
