"""Tests for LLM-driven policy key grouping and canonicalization parsing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from src.models.submission import PolicyCandidate, PolicyDomain
from src.pipeline.canonicalize import _sanitize_policy_slug
from src.pipeline.cluster import compute_centroid, group_by_policy_key


@dataclass
class FakeCandidate:
    id: UUID
    domain: PolicyDomain
    embedding: list[float] | None
    policy_key: str
    policy_topic: str
    title: str = ""
    summary: str = ""
    stance: str = "neutral"


class TestSanitizePolicySlug:
    def test_basic_slug(self) -> None:
        assert _sanitize_policy_slug("internet-censorship") == "internet-censorship"

    def test_uppercase_normalized(self) -> None:
        assert _sanitize_policy_slug("Internet-Censorship") == "internet-censorship"

    def test_underscores_to_hyphens(self) -> None:
        assert _sanitize_policy_slug("internet_censorship") == "internet-censorship"

    def test_spaces_to_hyphens(self) -> None:
        assert _sanitize_policy_slug("internet censorship") == "internet-censorship"

    def test_double_hyphens_collapsed(self) -> None:
        assert _sanitize_policy_slug("internet--censorship") == "internet-censorship"

    def test_leading_trailing_stripped(self) -> None:
        assert _sanitize_policy_slug("-internet-censorship-") == "internet-censorship"

    def test_empty_returns_unassigned(self) -> None:
        assert _sanitize_policy_slug("") == "unassigned"

    def test_whitespace_only_returns_unassigned(self) -> None:
        assert _sanitize_policy_slug("   ") == "unassigned"


class TestGroupByPolicyKey:
    def test_groups_by_key(self) -> None:
        c1 = FakeCandidate(
            id=uuid4(), domain=PolicyDomain.RIGHTS, embedding=[0.0],
            policy_key="mandatory-hijab-policy", policy_topic="dress-code-policy",
        )
        c2 = FakeCandidate(
            id=uuid4(), domain=PolicyDomain.RIGHTS, embedding=[0.0],
            policy_key="mandatory-hijab-policy", policy_topic="dress-code-policy",
        )
        c3 = FakeCandidate(
            id=uuid4(), domain=PolicyDomain.RIGHTS, embedding=[0.0],
            policy_key="political-internet-censorship", policy_topic="internet-censorship",
        )
        candidates = cast(list[PolicyCandidate], [c1, c2, c3])
        groups = group_by_policy_key(candidates=candidates)

        assert len(groups) == 2
        assert len(groups["mandatory-hijab-policy"]) == 2
        assert len(groups["political-internet-censorship"]) == 1

    def test_skips_unassigned(self) -> None:
        c1 = FakeCandidate(
            id=uuid4(), domain=PolicyDomain.OTHER, embedding=None,
            policy_key="unassigned", policy_topic="unassigned",
        )
        c2 = FakeCandidate(
            id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=[0.0],
            policy_key="youth-employment", policy_topic="economic-reform",
        )
        candidates = cast(list[PolicyCandidate], [c1, c2])
        groups = group_by_policy_key(candidates=candidates)

        assert "unassigned" not in groups
        assert len(groups) == 1

    def test_empty_input(self) -> None:
        groups = group_by_policy_key(candidates=[])
        assert groups == {}

    def test_single_key(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(
                    id=uuid4(), domain=PolicyDomain.ECONOMY, embedding=[0.0],
                    policy_key="death-penalty", policy_topic="judicial-reform",
                )
                for _ in range(5)
            ],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert len(groups) == 1
        assert len(groups["death-penalty"]) == 5

    def test_mixed_stances_same_key(self) -> None:
        """Different stances on the same policy land in the same group."""
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(
                    id=uuid4(), domain=PolicyDomain.RIGHTS, embedding=[0.0],
                    policy_key="mandatory-hijab-policy", policy_topic="dress-code-policy",
                    stance=stance,
                )
                for stance in ["support", "oppose", "neutral", "support", "support"]
            ],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert len(groups) == 1
        assert len(groups["mandatory-hijab-policy"]) == 5


class TestComputeCentroid:
    def test_simple_centroid(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(
                    id=uuid4(), domain=PolicyDomain.ECONOMY,
                    embedding=[0.0, 0.0], policy_key="test", policy_topic="test",
                ),
                FakeCandidate(
                    id=uuid4(), domain=PolicyDomain.ECONOMY,
                    embedding=[4.0, 4.0], policy_key="test", policy_topic="test",
                ),
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
                FakeCandidate(
                    id=uuid4(), domain=PolicyDomain.ECONOMY,
                    embedding=[2.0, 2.0], policy_key="test", policy_topic="test",
                ),
                FakeCandidate(
                    id=uuid4(), domain=PolicyDomain.ECONOMY,
                    embedding=None, policy_key="test", policy_topic="test",
                ),
            ],
        )
        centroid = compute_centroid(candidates)
        assert centroid is not None
        assert abs(centroid[0] - 2.0) < 1e-6

    def test_all_none_returns_none(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                FakeCandidate(
                    id=uuid4(), domain=PolicyDomain.ECONOMY,
                    embedding=None, policy_key="test", policy_topic="test",
                ),
            ],
        )
        assert compute_centroid(candidates) is None
