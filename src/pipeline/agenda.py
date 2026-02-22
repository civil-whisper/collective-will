from __future__ import annotations

from dataclasses import dataclass

from src.models.cluster import Cluster


@dataclass(slots=True)
class AgendaItem:
    cluster_id: str
    qualifies: bool
    member_count: int
    endorsement_count: int
    reason: str


def build_agenda(
    *,
    clusters: list[Cluster],
    endorsement_counts: dict[str, int],
    min_cluster_size: int,
    min_preballot_endorsements: int,
) -> list[AgendaItem]:
    items: list[AgendaItem] = []
    for cluster in clusters:
        endorsements = endorsement_counts.get(str(cluster.id), 0)
        size_ok = cluster.member_count >= min_cluster_size
        endorsements_ok = endorsements >= min_preballot_endorsements
        qualifies = size_ok and endorsements_ok
        if not size_ok:
            reason = "below_size_threshold"
        elif not endorsements_ok:
            reason = "below_endorsement_threshold"
        else:
            reason = "qualified"
        items.append(
            AgendaItem(
                cluster_id=str(cluster.id),
                qualifies=qualifies,
                member_count=cluster.member_count,
                endorsement_count=endorsements,
                reason=reason,
            )
        )
    return items
