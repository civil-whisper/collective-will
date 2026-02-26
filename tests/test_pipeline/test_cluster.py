from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import numpy as np

from src.models.submission import PolicyCandidate
from src.pipeline.cluster import compute_centroid, group_by_policy_key


@dataclass
class FakeCandidate:
    id: UUID
    embedding: list[float] | None
    policy_key: str = "test-policy"
    policy_topic: str = "test-topic"


class TestGroupByPolicyKey:
    def test_groups_by_key(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(id=uuid4(), embedding=[0.0], policy_key="healthcare-access"),
                FakeCandidate(id=uuid4(), embedding=[0.0], policy_key="healthcare-access"),
                FakeCandidate(id=uuid4(), embedding=[0.0], policy_key="internet-censorship"),
            ],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert len(groups) == 2
        assert len(groups["healthcare-access"]) == 2
        assert len(groups["internet-censorship"]) == 1

    def test_skips_unassigned(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(id=uuid4(), embedding=[0.0], policy_key="unassigned"),
                FakeCandidate(id=uuid4(), embedding=[0.0], policy_key="real-policy"),
            ],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert len(groups) == 1
        assert "unassigned" not in groups

    def test_empty_candidates(self) -> None:
        groups = group_by_policy_key(candidates=[])
        assert groups == {}

    def test_single_key_many_candidates(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [FakeCandidate(id=uuid4(), embedding=[0.0], policy_key="housing") for _ in range(5)],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert len(groups) == 1
        assert len(groups["housing"]) == 5


class TestComputeCentroid:
    def test_simple_centroid(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(id=uuid4(), embedding=[0.0, 0.0]),
                FakeCandidate(id=uuid4(), embedding=[4.0, 4.0]),
            ],
        )
        centroid = compute_centroid(candidates)
        assert centroid is not None
        assert abs(centroid[0] - 2.0) < 1e-6
        assert abs(centroid[1] - 2.0) < 1e-6

    def test_none_embeddings_excluded(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(id=uuid4(), embedding=[2.0, 2.0]),
                FakeCandidate(id=uuid4(), embedding=None),
            ],
        )
        centroid = compute_centroid(candidates)
        assert centroid is not None
        assert abs(centroid[0] - 2.0) < 1e-6

    def test_all_none_returns_none(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [FakeCandidate(id=uuid4(), embedding=None)],
        )
        assert compute_centroid(candidates) is None

    def test_empty_list_returns_none(self) -> None:
        assert compute_centroid([]) is None

    def test_numpy_embeddings(self) -> None:
        """pgvector returns numpy arrays — verify no truth-value error."""
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(id=uuid4(), embedding=np.array([1.0, 3.0])),  # type: ignore[arg-type]
                FakeCandidate(id=uuid4(), embedding=np.array([3.0, 1.0])),  # type: ignore[arg-type]
            ],
        )
        centroid = compute_centroid(candidates)
        assert centroid is not None
        assert abs(centroid[0] - 2.0) < 1e-6
        assert abs(centroid[1] - 2.0) < 1e-6
