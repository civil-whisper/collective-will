from __future__ import annotations

from collections import defaultdict

import numpy as np

from src.models.submission import PolicyCandidate


def group_by_policy_key(
    *,
    candidates: list[PolicyCandidate],
) -> dict[str, list[PolicyCandidate]]:
    """Group candidates by their LLM-assigned policy_key."""
    groups: dict[str, list[PolicyCandidate]] = defaultdict(list)
    for candidate in candidates:
        key = candidate.policy_key
        if key and key != "unassigned":
            groups[key].append(candidate)
    return dict(groups)


def compute_centroid(candidates: list[PolicyCandidate]) -> list[float] | None:
    """Compute centroid embedding from candidates that have embeddings."""
    points = []
    for c in candidates:
        if c.embedding is not None:
            points.append([float(v) for v in c.embedding])
    if not points:
        return None
    arr = np.array(points, dtype=float)
    return list(arr.mean(axis=0).tolist())
