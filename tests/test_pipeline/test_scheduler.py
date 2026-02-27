from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.pipeline.llm import LLMResponse
from src.scheduler import (
    PipelineResult,
    _close_expired_cycles,
    _count_unprocessed,
    _maybe_open_cycle,
    run_pipeline,
)


class FakeScalars:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return self._items

    def first(self) -> object | None:
        return self._items[0] if self._items else None


class FakeResult:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._items)

    def scalar_one_or_none(self) -> object | None:
        return self._items[0] if self._items else None

    def all(self) -> list[object]:
        return self._items


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
    assert result.opened_cycle_id is None
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
async def test_close_expired_cycles_standalone() -> None:
    """_close_expired_cycles closes expired cycles without running full pipeline."""
    expired_cycle = _FakeCycle()

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=FakeResult([expired_cycle]))

    mock_tally = AsyncMock(return_value=expired_cycle)
    with patch("src.scheduler.main.close_and_tally", mock_tally):
        closed = await _close_expired_cycles(session)

    assert closed == 1
    mock_tally.assert_called_once_with(session=session, cycle=expired_cycle)


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


# --- _count_unprocessed tests ---


@pytest.mark.asyncio
async def test_count_unprocessed_returns_count() -> None:
    scalar_mock = MagicMock()
    scalar_mock.scalar_one.return_value = 7
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=scalar_mock)

    count = await _count_unprocessed(session)  # type: ignore[arg-type]
    assert count == 7
    session.execute.assert_called_once()


# --- scheduler_loop hybrid trigger tests ---


@pytest.mark.asyncio
async def test_scheduler_loop_threshold_trigger() -> None:
    """Pipeline runs again when unprocessed count reaches batch_threshold."""
    run_count = 0

    async def _fake_run_pipeline(*, session: object, **kw: object) -> PipelineResult:
        nonlocal run_count
        run_count += 1
        if run_count >= 2:
            raise _StopLoop
        return PipelineResult()

    poll_count = 0

    async def _fake_count(session: object) -> int:
        nonlocal poll_count
        poll_count += 1
        return 10

    from src.scheduler.main import scheduler_loop

    fake_session = AsyncMock()
    fake_factory = AsyncMock()
    fake_factory.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.__aexit__ = AsyncMock(return_value=False)

    def _session_factory() -> object:
        return fake_factory

    with (
        patch("src.scheduler.main.run_pipeline", side_effect=_fake_run_pipeline),
        patch("src.scheduler.main._count_unprocessed", side_effect=_fake_count),
        patch("src.scheduler.main._close_expired_cycles", new_callable=AsyncMock, return_value=0),
        patch("src.scheduler.main._maybe_open_cycle", new_callable=AsyncMock, return_value=None),
        patch("src.scheduler.main.upsert_heartbeat", new_callable=AsyncMock),
        pytest.raises(_StopLoop),
    ):
        await scheduler_loop(
            session_factory=_session_factory,
            interval_hours=1.0,
            min_interval_hours=0.001,
            batch_threshold=10,
            poll_seconds=0.01,
        )

    assert run_count == 2
    assert poll_count >= 1


@pytest.mark.asyncio
async def test_scheduler_loop_time_trigger() -> None:
    """Pipeline runs after max interval even when below threshold."""
    run_count = 0

    async def _fake_run_pipeline(*, session: object, **kw: object) -> PipelineResult:
        nonlocal run_count
        run_count += 1
        if run_count >= 2:
            raise _StopLoop
        return PipelineResult()

    async def _always_zero(session: object) -> int:
        return 0

    from src.scheduler.main import scheduler_loop

    fake_session = AsyncMock()
    fake_factory = AsyncMock()
    fake_factory.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.__aexit__ = AsyncMock(return_value=False)

    def _session_factory() -> object:
        return fake_factory

    with (
        patch("src.scheduler.main.run_pipeline", side_effect=_fake_run_pipeline),
        patch("src.scheduler.main._count_unprocessed", side_effect=_always_zero),
        patch("src.scheduler.main._close_expired_cycles", new_callable=AsyncMock, return_value=0),
        patch("src.scheduler.main._maybe_open_cycle", new_callable=AsyncMock, return_value=None),
        patch("src.scheduler.main.upsert_heartbeat", new_callable=AsyncMock),
        pytest.raises(_StopLoop),
    ):
        await scheduler_loop(
            session_factory=_session_factory,
            interval_hours=0.0001,
            min_interval_hours=0.0001,
            batch_threshold=999,
            poll_seconds=0.01,
        )

    assert run_count == 2


@pytest.mark.asyncio
async def test_scheduler_loop_skips_pipeline_below_threshold() -> None:
    """Pipeline does NOT run when count stays below threshold and interval hasn't elapsed."""
    run_count = 0

    async def _fake_run_pipeline(*, session: object, **kw: object) -> PipelineResult:
        nonlocal run_count
        run_count += 1
        return PipelineResult()

    poll_count = 0

    async def _fake_count(session: object) -> int:
        nonlocal poll_count
        poll_count += 1
        if poll_count >= 5:
            raise _StopLoop
        return 3

    from src.scheduler.main import scheduler_loop

    fake_session = AsyncMock()
    fake_factory = AsyncMock()
    fake_factory.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.__aexit__ = AsyncMock(return_value=False)

    def _session_factory() -> object:
        return fake_factory

    with (
        patch("src.scheduler.main.run_pipeline", side_effect=_fake_run_pipeline),
        patch("src.scheduler.main._count_unprocessed", side_effect=_fake_count),
        patch("src.scheduler.main._close_expired_cycles", new_callable=AsyncMock, return_value=0),
        patch("src.scheduler.main._maybe_open_cycle", new_callable=AsyncMock, return_value=None),
        patch("src.scheduler.main.upsert_heartbeat", new_callable=AsyncMock),
        pytest.raises(_StopLoop),
    ):
        await scheduler_loop(
            session_factory=_session_factory,
            interval_hours=1.0,
            min_interval_hours=1.0,
            batch_threshold=10,
            poll_seconds=0.01,
        )

    assert run_count == 0, "Pipeline should not run when count stays below threshold"
    assert poll_count >= 2


class _StopLoop(Exception):
    """Raised to break out of the infinite scheduler loop in tests."""


# --- _find_or_create_cluster evidence event tests ---


@pytest.mark.asyncio
async def test_find_or_create_cluster_emits_cluster_created() -> None:
    """New clusters should produce a cluster_created evidence event."""
    from src.scheduler.main import _find_or_create_cluster

    cluster_id = uuid4()
    candidate = SimpleNamespace(id=uuid4(), policy_topic="economy", policy_key="tax-reform")
    fake_cluster = SimpleNamespace(id=cluster_id, policy_key="tax-reform")

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=FakeResult([]))
    session.flush = AsyncMock()

    with (
        patch("src.scheduler.main.create_cluster", new_callable=AsyncMock, return_value=fake_cluster) as _,
        patch("src.scheduler.main.append_evidence", new_callable=AsyncMock) as mock_evidence,
    ):
        result = await _find_or_create_cluster(
            session=session, policy_key="tax-reform", members=[candidate],
        )

    assert result is fake_cluster
    mock_evidence.assert_called_once()
    call_kwargs = mock_evidence.call_args[1]
    assert call_kwargs["event_type"] == "cluster_created"
    assert call_kwargs["entity_type"] == "cluster"
    assert call_kwargs["entity_id"] == cluster_id
    assert call_kwargs["payload"]["policy_key"] == "tax-reform"
    assert call_kwargs["payload"]["policy_topic"] == "economy"


@pytest.mark.asyncio
async def test_find_or_create_cluster_emits_cluster_updated() -> None:
    """Existing clusters gaining new members should produce a cluster_updated event."""
    from src.scheduler.main import _find_or_create_cluster

    cluster_id = uuid4()
    old_member_id = uuid4()
    new_member_id = uuid4()

    existing = SimpleNamespace(
        id=cluster_id,
        policy_key="tax-reform",
        candidate_ids=[old_member_id],
        member_count=1,
        needs_resummarize=False,
    )
    new_candidate = SimpleNamespace(id=new_member_id, policy_topic="economy", policy_key="tax-reform")

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=FakeResult([existing]))
    session.flush = AsyncMock()

    with patch("src.scheduler.main.append_evidence", new_callable=AsyncMock) as mock_evidence:
        result = await _find_or_create_cluster(
            session=session, policy_key="tax-reform", members=[new_candidate],
        )

    assert result is existing
    assert existing.member_count == 2
    mock_evidence.assert_called_once()
    call_kwargs = mock_evidence.call_args[1]
    assert call_kwargs["event_type"] == "cluster_updated"
    assert call_kwargs["entity_type"] == "cluster"
    assert call_kwargs["payload"]["old_member_count"] == 1
    assert call_kwargs["payload"]["new_member_count"] == 2


@pytest.mark.asyncio
async def test_find_or_create_cluster_skips_event_when_no_change() -> None:
    """No evidence event if existing cluster already contains all the members."""
    from src.scheduler.main import _find_or_create_cluster

    member_id = uuid4()
    existing = SimpleNamespace(
        id=uuid4(),
        policy_key="tax-reform",
        candidate_ids=[member_id],
        member_count=1,
        needs_resummarize=False,
    )
    same_candidate = SimpleNamespace(id=member_id, policy_topic="economy", policy_key="tax-reform")

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=FakeResult([existing]))
    session.flush = AsyncMock()

    with patch("src.scheduler.main.append_evidence", new_callable=AsyncMock) as mock_evidence:
        await _find_or_create_cluster(
            session=session, policy_key="tax-reform", members=[same_candidate],
        )

    mock_evidence.assert_not_called()


# --- _maybe_open_cycle tests ---


class _FakeCluster:
    """Minimal Cluster stand-in for _maybe_open_cycle tests."""

    def __init__(
        self, *, member_count: int = 5, ballot_question: str | None = "Q?",
        needs_resummarize: bool = False, policy_key: str = "clean-water",
        status: str = "open",
    ) -> None:
        self.id = uuid4()
        self.policy_key = policy_key
        self.member_count = member_count
        self.ballot_question = ballot_question
        self.needs_resummarize = needs_resummarize
        self.status = status


def _settings_patch(**overrides: object) -> MagicMock:
    defaults = {
        "min_preballot_endorsements": 5,
        "auto_cycle_cooldown_hours": 0,
    }
    defaults.update(overrides)
    s = MagicMock()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


@pytest.mark.asyncio
async def test_maybe_open_cycle_opens_when_qualified() -> None:
    cluster = _FakeCluster(member_count=5)
    cycle_obj = MagicMock()
    cycle_obj.id = uuid4()

    call_idx = 0

    async def _fake_execute(stmt: object, *a: object, **kw: object) -> FakeResult:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return FakeResult([])  # no active cycle
        if call_idx == 2:
            return FakeResult([cluster])  # open clusters
        return FakeResult([])

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_fake_execute)

    with (
        patch("src.scheduler.main.get_settings", return_value=_settings_patch()),
        patch("src.scheduler.main.count_cluster_endorsements", new_callable=AsyncMock, return_value=0),
        patch("src.scheduler.main._has_options", new_callable=AsyncMock, return_value=True),
        patch("src.scheduler.main.open_cycle", new_callable=AsyncMock, return_value=cycle_obj) as mock_open,
    ):
        result = await _maybe_open_cycle(session)

    assert result is cycle_obj
    mock_open.assert_called_once()
    opened_ids = mock_open.call_args.kwargs["cluster_ids"]
    assert cluster.id in opened_ids


@pytest.mark.asyncio
async def test_maybe_open_cycle_skips_when_active_cycle_exists() -> None:
    active_cycle = _FakeCycle()

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=FakeResult([active_cycle]))

    with patch("src.scheduler.main.get_settings", return_value=_settings_patch()):
        result = await _maybe_open_cycle(session)

    assert result is None


@pytest.mark.asyncio
async def test_maybe_open_cycle_respects_cooldown() -> None:
    recently_closed = MagicMock()
    recently_closed.ends_at = datetime.now(UTC) - timedelta(minutes=10)

    call_idx = 0

    async def _fake_execute(stmt: object, *a: object, **kw: object) -> FakeResult:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return FakeResult([])  # no active cycle
        if call_idx == 2:
            return FakeResult([recently_closed])  # last closed cycle
        return FakeResult([])

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_fake_execute)

    with patch("src.scheduler.main.get_settings", return_value=_settings_patch(auto_cycle_cooldown_hours=1)):
        result = await _maybe_open_cycle(session)

    assert result is None


@pytest.mark.asyncio
async def test_maybe_open_cycle_skips_when_below_threshold() -> None:
    cluster = _FakeCluster(member_count=2)  # only 2 submissions, threshold is 5

    call_idx = 0

    async def _fake_execute(stmt: object, *a: object, **kw: object) -> FakeResult:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return FakeResult([])  # no active cycle
        if call_idx == 2:
            return FakeResult([cluster])  # open clusters
        return FakeResult([])

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_fake_execute)

    with (
        patch("src.scheduler.main.get_settings", return_value=_settings_patch()),
        patch("src.scheduler.main.count_cluster_endorsements", new_callable=AsyncMock, return_value=0),
        patch("src.scheduler.main._has_options", new_callable=AsyncMock, return_value=True),
    ):
        result = await _maybe_open_cycle(session)

    assert result is None


@pytest.mark.asyncio
async def test_maybe_open_cycle_skips_without_ballot_question() -> None:
    cluster = _FakeCluster(member_count=5, ballot_question=None)

    call_idx = 0

    async def _fake_execute(stmt: object, *a: object, **kw: object) -> FakeResult:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return FakeResult([])  # no active cycle
        if call_idx == 2:
            return FakeResult([cluster])  # open clusters
        return FakeResult([])

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_fake_execute)

    with (
        patch("src.scheduler.main.get_settings", return_value=_settings_patch()),
        patch("src.scheduler.main.count_cluster_endorsements", new_callable=AsyncMock, return_value=0),
        patch("src.scheduler.main._has_options", new_callable=AsyncMock, return_value=True),
    ):
        result = await _maybe_open_cycle(session)

    assert result is None


@pytest.mark.asyncio
async def test_maybe_open_cycle_skips_without_options() -> None:
    cluster = _FakeCluster(member_count=5)

    call_idx = 0

    async def _fake_execute(stmt: object, *a: object, **kw: object) -> FakeResult:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return FakeResult([])  # no active cycle
        if call_idx == 2:
            return FakeResult([cluster])  # open clusters
        return FakeResult([])

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_fake_execute)

    with (
        patch("src.scheduler.main.get_settings", return_value=_settings_patch()),
        patch("src.scheduler.main.count_cluster_endorsements", new_callable=AsyncMock, return_value=0),
        patch("src.scheduler.main._has_options", new_callable=AsyncMock, return_value=False),
    ):
        result = await _maybe_open_cycle(session)

    assert result is None


@pytest.mark.asyncio
async def test_maybe_open_cycle_skips_when_no_open_clusters() -> None:
    """When all clusters are archived (query returns empty), no cycle opens."""
    call_idx = 0

    async def _fake_execute(stmt: object, *a: object, **kw: object) -> FakeResult:
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return FakeResult([])  # no active cycle
        if call_idx == 2:
            return FakeResult([])  # no open clusters (all archived)
        return FakeResult([])

    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(side_effect=_fake_execute)

    with patch("src.scheduler.main.get_settings", return_value=_settings_patch()):
        result = await _maybe_open_cycle(session)

    assert result is None
