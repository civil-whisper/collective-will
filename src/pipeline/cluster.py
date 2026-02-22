from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID, uuid4

import hdbscan
import numpy as np

from src.models.cluster import ClusterCreate
from src.models.submission import PolicyCandidate, PolicyDomain


@dataclass(slots=True)
class ClusterRunResult:
    clusters: list[ClusterCreate]
    noise_candidate_ids: list[UUID]
    run_id: str
    random_seed: int
    clustering_params: dict[str, int]


def _majority_domain(candidates: Iterable[PolicyCandidate]) -> PolicyDomain:
    domains = [candidate.domain for candidate in candidates]
    if not domains:
        return PolicyDomain.OTHER
    return Counter(domains).most_common(1)[0][0]


def run_clustering(
    *,
    candidates: list[PolicyCandidate],
    cycle_id: UUID,
    min_cluster_size: int = 5,
    random_seed: int = 42,
) -> ClusterRunResult:
    embeddings: list[list[float]] = []
    embedded_candidates: list[PolicyCandidate] = []
    for candidate in candidates:
        if candidate.embedding:
            embeddings.append([float(v) for v in candidate.embedding])
            embedded_candidates.append(candidate)

    run_id = str(uuid4())
    if len(embedded_candidates) < min_cluster_size:
        return ClusterRunResult(
            clusters=[],
            noise_candidate_ids=[candidate.id for candidate in embedded_candidates],
            run_id=run_id,
            random_seed=random_seed,
            clustering_params={"min_cluster_size": min_cluster_size},
        )

    arr = np.array(embeddings, dtype=float)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size)
    labels = clusterer.fit_predict(arr)

    groups: dict[int, list[PolicyCandidate]] = defaultdict(list)
    noise_ids: list[UUID] = []
    for candidate, label in zip(embedded_candidates, labels, strict=True):
        if int(label) == -1:
            noise_ids.append(candidate.id)
            continue
        groups[int(label)].append(candidate)

    clusters: list[ClusterCreate] = []
    for label, grouped in groups.items():
        points = np.array([[float(v) for v in candidate.embedding or []] for candidate in grouped])
        centroid = points.mean(axis=0).tolist() if len(points) else None
        cohesion = 0.0
        if len(points) > 1 and centroid is not None:
            dists = np.linalg.norm(points - np.array(centroid), axis=1)
            cohesion = float(max(0.0, 1.0 - float(np.mean(dists))))
        clusters.append(
            ClusterCreate(
                cycle_id=cycle_id,
                summary=f"Cluster {label}",
                domain=_majority_domain(grouped),
                candidate_ids=[candidate.id for candidate in grouped],
                member_count=len(grouped),
                centroid_embedding=centroid,
                cohesion_score=cohesion,
                variance_flag=False,
                run_id=run_id,
                random_seed=random_seed,
                clustering_params={"min_cluster_size": min_cluster_size},
                approval_count=0,
            )
        )

    return ClusterRunResult(
        clusters=clusters,
        noise_candidate_ids=noise_ids,
        run_id=run_id,
        random_seed=random_seed,
        clustering_params={"min_cluster_size": min_cluster_size},
    )


def variance_check(
    *,
    candidates: list[PolicyCandidate],
    cycle_id: UUID,
    min_cluster_size: int = 5,
    stability_threshold: float = 0.6,
) -> list[bool]:
    if len(candidates) < 20:
        return [False] * len(candidates)

    runs = [
        run_clustering(
            candidates=candidates,
            cycle_id=cycle_id,
            min_cluster_size=min_cluster_size,
            random_seed=seed,
        )
        for seed in (7, 11, 13)
    ]

    cluster_members = [set(member for c in run.clusters for member in c.candidate_ids) for run in runs]
    jaccards: list[float] = []
    for idx in range(len(cluster_members) - 1):
        a = cluster_members[idx]
        b = cluster_members[idx + 1]
        if not a and not b:
            jaccards.append(1.0)
        else:
            jaccards.append(len(a & b) / max(len(a | b), 1))
    stable = sum(jaccards) / len(jaccards) >= stability_threshold if jaccards else True
    return [not stable] * len(candidates)
