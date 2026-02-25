from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from src.models.cluster import Cluster
from src.pipeline.agenda import build_agenda


@dataclass
class FakeCluster:
    id: UUID
    member_count: int
    policy_key: str = "test-policy"


def test_cluster_qualifies_combined_support() -> None:
    c_id = uuid4()
    clusters = cast(list[Cluster], [FakeCluster(id=c_id, member_count=3)])
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={str(c_id): 2},
        min_support=5,
    )
    assert len(items) == 1
    assert items[0].qualifies is True
    assert items[0].total_support == 5
    assert items[0].reason == "qualified"


def test_cluster_below_support_excluded() -> None:
    c_id = uuid4()
    clusters = cast(list[Cluster], [FakeCluster(id=c_id, member_count=2)])
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={str(c_id): 1},
        min_support=5,
    )
    assert items[0].qualifies is False
    assert items[0].total_support == 3
    assert items[0].reason == "below_support_threshold"


def test_submissions_count_as_implicit_endorsements() -> None:
    """member_count alone can meet the support threshold (no explicit endorsements)."""
    c_id = uuid4()
    clusters = cast(list[Cluster], [FakeCluster(id=c_id, member_count=5)])
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={},
        min_support=5,
    )
    assert items[0].qualifies is True
    assert items[0].total_support == 5


def test_empty_cluster_set() -> None:
    items = build_agenda(
        clusters=[],
        endorsement_counts={},
        min_support=5,
    )
    assert items == []


def test_all_qualifying_clusters_included() -> None:
    clusters = cast(
        list[Cluster],
        [FakeCluster(id=uuid4(), member_count=10) for _ in range(5)],
    )
    endorsement_counts = {str(c.id): 10 for c in clusters}
    items = build_agenda(
        clusters=clusters,
        endorsement_counts=endorsement_counts,
        min_support=5,
    )
    assert sum(1 for item in items if item.qualifies) == 5


def test_policy_key_carried_through() -> None:
    c_id = uuid4()
    clusters = cast(
        list[Cluster],
        [FakeCluster(id=c_id, member_count=10, policy_key="healthcare-access")],
    )
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={str(c_id): 3},
        min_support=5,
    )
    assert items[0].policy_key == "healthcare-access"
