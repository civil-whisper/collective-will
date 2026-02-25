from __future__ import annotations

from dataclasses import dataclass

from src.models.cluster import Cluster


@dataclass(slots=True)
class AgendaItem:
    cluster_id: str
    policy_key: str
    qualifies: bool
    member_count: int
    endorsement_count: int
    total_support: int
    reason: str


def build_agenda(
    *,
    clusters: list[Cluster],
    endorsement_counts: dict[str, int],
    min_support: int,
) -> list[AgendaItem]:
    """Build the voting agenda.

    Qualification uses a single combined gate: submissions (member_count)
    count as implicit endorsements, plus explicit endorsements from users
    who didn't submit.
    """
    items: list[AgendaItem] = []
    for cluster in clusters:
        endorsements = endorsement_counts.get(str(cluster.id), 0)
        total_support = cluster.member_count + endorsements
        qualifies = total_support >= min_support
        reason = "qualified" if qualifies else "below_support_threshold"
        items.append(
            AgendaItem(
                cluster_id=str(cluster.id),
                policy_key=cluster.policy_key,
                qualifies=qualifies,
                member_count=cluster.member_count,
                endorsement_count=endorsements,
                total_support=total_support,
                reason=reason,
            )
        )
    return items
