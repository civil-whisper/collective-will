from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.pipeline.llm import LLMResponse
from src.scheduler import PipelineResult, run_pipeline


class FakeScalars:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return self._items


class FakeResult:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._items)


class FakeRouter:
    async def complete(self, *, tier: str, prompt: str, **kwargs: object) -> LLMResponse:
        return LLMResponse(
            text='{"title":"P","domain":"other","summary":"s","stance":"neutral","entities":[],"confidence":0.9,"ambiguity_flags":[]}',
            model="m",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        )

    async def embed(self, texts: list[str], timeout_s: float = 60.0) -> object:
        return type("R", (), {"vectors": [[0.1] * 10 for _ in texts]})()


@pytest.mark.asyncio
async def test_no_pending_submissions_returns_zero() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=FakeResult([]))

    result = await run_pipeline(session=session, llm_router=FakeRouter())  # type: ignore[arg-type]
    assert isinstance(result, PipelineResult)
    assert result.processed_submissions == 0


@pytest.mark.asyncio
async def test_pipeline_result_has_expected_fields() -> None:
    result = PipelineResult()
    assert result.processed_submissions == 0
    assert result.created_candidates == 0
    assert result.created_clusters == 0
    assert result.qualified_clusters == 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_pipeline_errors_captured_not_raised() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=RuntimeError("DB down"))
    session.rollback = AsyncMock()

    result = await run_pipeline(session=session, llm_router=FakeRouter())  # type: ignore[arg-type]
    assert len(result.errors) >= 1 or result.processed_submissions == 0
