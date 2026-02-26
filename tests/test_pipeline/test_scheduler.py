from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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


class _FakeCycle:
    """Minimal stand-in for VotingCycle with an expired ends_at."""

    def __init__(self) -> None:
        self.id = uuid4()
        self.status = "active"
        self.ends_at = datetime.now(UTC) - timedelta(hours=1)
        self.cluster_ids: list[object] = []


@pytest.mark.asyncio
async def test_expired_cycle_auto_closed() -> None:
    expired_cycle = _FakeCycle()

    call_count = 0

    async def _fake_execute(stmt: object, *a: object, **kw: object) -> FakeResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return FakeResult([expired_cycle])
        return FakeResult([])

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_fake_execute)

    mock_tally = AsyncMock(return_value=expired_cycle)
    with patch("src.scheduler.main.close_and_tally", mock_tally):
        result = await run_pipeline(session=session, llm_router=FakeRouter())  # type: ignore[arg-type]

    mock_tally.assert_called_once_with(session=session, cycle=expired_cycle)
    assert result.processed_submissions == 0


@pytest.mark.asyncio
async def test_batch_canonicalization_increments_contribution_count() -> None:
    """Pending submissions that get batch-canonicalized should increment their user's contribution_count."""
    sub_id = uuid4()
    fake_user = SimpleNamespace(id=uuid4(), contribution_count=0)
    fake_sub = SimpleNamespace(
        id=sub_id,
        user_id=fake_user.id,
        user=fake_user,
        raw_text="need clean water",
        language="en",
        status="pending",
        candidates=[],
        created_at=datetime.now(UTC),
    )

    candidate_create = MagicMock()
    candidate_create.submission_id = sub_id

    call_count = 0

    async def _fake_execute(stmt: object, *a: object, **kw: object) -> FakeResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return FakeResult([])
        if call_count == 2:
            return FakeResult([fake_sub])
        return FakeResult([])

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_fake_execute)
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    mock_candidate = MagicMock()
    mock_candidate.id = uuid4()
    mock_candidate.embedding = None
    mock_candidate.policy_key = "clean-water"
    mock_candidate.policy_topic = "environment"

    with (
        patch("src.scheduler.main.load_existing_policy_context", new_callable=AsyncMock, return_value={}),
        patch("src.scheduler.main.canonicalize_batch", new_callable=AsyncMock, return_value=[candidate_create]),
        patch("src.scheduler.main.create_policy_candidate", new_callable=AsyncMock, return_value=mock_candidate),
        patch("src.scheduler.main.compute_and_store_embeddings", new_callable=AsyncMock),
        patch("src.scheduler.main.normalize_policy_keys", new_callable=AsyncMock, return_value=[]),
        patch("src.scheduler.main._find_or_create_cluster", new_callable=AsyncMock),
        patch("src.scheduler.main.generate_ballot_questions", new_callable=AsyncMock),
        patch("src.scheduler.main.generate_policy_options", new_callable=AsyncMock),
        patch("src.scheduler.main.build_agenda", return_value=[]),
        patch("src.scheduler.main._run_daily_anchoring", new_callable=AsyncMock),
    ):
        fake_sub.candidates = [mock_candidate]

        result = await run_pipeline(session=session, llm_router=FakeRouter())  # type: ignore[arg-type]

    assert fake_user.contribution_count == 1
    assert result.processed_submissions == 1
