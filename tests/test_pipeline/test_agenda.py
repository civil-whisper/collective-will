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


def test_cluster_qualifies_with_both_gates() -> None:
    c_id = uuid4()
    clusters = cast(list[Cluster], [FakeCluster(id=c_id, member_count=5)])
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={str(c_id): 5},
        min_cluster_size=5,
        min_preballot_endorsements=5,
    )
    assert len(items) == 1
    assert items[0].qualifies is True
    assert items[0].reason == "qualified"


def test_cluster_below_size_excluded() -> None:
    c_id = uuid4()
    clusters = cast(list[Cluster], [FakeCluster(id=c_id, member_count=3)])
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={str(c_id): 10},
        min_cluster_size=5,
        min_preballot_endorsements=5,
    )
    assert items[0].qualifies is False
    assert items[0].reason == "below_size_threshold"


def test_cluster_below_endorsement_excluded() -> None:
    c_id = uuid4()
    clusters = cast(list[Cluster], [FakeCluster(id=c_id, member_count=10)])
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={str(c_id): 2},
        min_cluster_size=5,
        min_preballot_endorsements=5,
    )
    assert items[0].qualifies is False
    assert items[0].reason == "below_endorsement_threshold"


def test_empty_cluster_set() -> None:
    items = build_agenda(
        clusters=[],
        endorsement_counts={},
        min_cluster_size=5,
        min_preballot_endorsements=5,
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
        min_cluster_size=5,
        min_preballot_endorsements=5,
    )
    assert sum(1 for item in items if item.qualifies) == 5
