from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.models.submission import PolicyDomain
from src.pipeline.llm import LLMResponse
from src.pipeline.summarize import determine_cluster_domain


@dataclass
class FakePolicyCandidate:
    id: UUID
    title: str
    summary: str
    domain: PolicyDomain


@dataclass
class FakeCluster:
    id: UUID
    candidate_ids: list[UUID]
    summary: str = ""
    summary_en: str | None = None
    domain: PolicyDomain = PolicyDomain.OTHER


class FakeRouter:
    def __init__(self, text: str = '{"summary":"خلاصه","summary_en":"Summary","grouping_rationale":"reason"}') -> None:
        self.calls: list[str] = []
        self._text = text

    async def complete(self, *, tier: str, prompt: str, **kwargs: object) -> LLMResponse:
        self.calls.append(tier)
        return LLMResponse(
            text=self._text, model="claude-sonnet-latest", input_tokens=10, output_tokens=5, cost_usd=0.0
        )


def test_determine_cluster_domain_majority() -> None:
    candidates = [
        FakePolicyCandidate(id=uuid4(), title="A", summary="A", domain=PolicyDomain.ECONOMY),
        FakePolicyCandidate(id=uuid4(), title="B", summary="B", domain=PolicyDomain.ECONOMY),
        FakePolicyCandidate(id=uuid4(), title="C", summary="C", domain=PolicyDomain.RIGHTS),
    ]
    assert determine_cluster_domain(candidates) == PolicyDomain.ECONOMY  # type: ignore[arg-type]


def test_determine_cluster_domain_empty() -> None:
    assert determine_cluster_domain([]) == PolicyDomain.OTHER


@pytest.mark.asyncio
async def test_summarize_generates_summary() -> None:
    from src.pipeline.summarize import summarize_clusters

    c_id = uuid4()
    candidate = FakePolicyCandidate(id=c_id, title="Policy A", summary="Summary A", domain=PolicyDomain.ECONOMY)
    cluster = FakeCluster(id=uuid4(), candidate_ids=[c_id])
    candidates_by_id = {c_id: candidate}
    router = FakeRouter()
    session = AsyncMock()

    @asynccontextmanager
    async def _begin_nested() -> AsyncIterator[None]:
        yield

    session.begin_nested = _begin_nested
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    result = await summarize_clusters(
        session=session,
        clusters=[cluster],  # type: ignore[list-item]
        candidates_by_id=candidates_by_id,  # type: ignore[arg-type]
        llm_router=router,  # type: ignore[arg-type]
    )
    assert len(result) == 1
    assert result[0].summary != ""
    assert router.calls[0] == "english_reasoning"
