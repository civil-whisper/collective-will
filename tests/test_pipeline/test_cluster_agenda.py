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


def test_agenda_threshold_gating() -> None:
    cluster_id = uuid4()
    clusters = cast(list[Cluster], [FakeCluster(id=cluster_id, member_count=5)])
    items = build_agenda(
        clusters=clusters,
        endorsement_counts={str(cluster_id): 5},
        min_support=5,
    )
    assert items[0].qualifies is True
