from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.queries import (
    create_policy_candidate,
    create_submission,
    create_user,
    create_voting_cycle,
)
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidateCreate, PolicyDomain, SubmissionCreate
from src.models.user import UserCreate
from src.models.vote import VotingCycle, VotingCycleCreate
from src.pipeline.canonicalize import canonicalize_batch
from src.pipeline.embeddings import compute_and_store_embeddings, prepare_text_for_embedding
from src.pipeline.llm import LLMResponse
from src.scheduler import run_pipeline


class FakeRouter:
    def __init__(self) -> None:
        self._embed_counter = 0

    async def complete(self, *, tier: str, prompt: str, timeout_s: float = 60.0, **kwargs: object) -> LLMResponse:
        return LLMResponse(
            text='{"title":"Policy","domain":"economy","summary":"s","stance":"unclear","entities":[],"confidence":0.5,"ambiguity_flags":[]}',
            model="claude-sonnet-4-20250514",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        )

    async def embed(self, texts: list[str], timeout_s: float = 30.0):  # type: ignore[no-untyped-def]
        import numpy as np

        rng = np.random.RandomState(42)
        vecs: list[list[float]] = []
        for _text in texts:
            self._embed_counter += 1
            center = 0.0 if self._embed_counter % 2 == 0 else 10.0
            vecs.append(rng.normal(center, 0.1, 1024).tolist())

        class R:
            vectors = vecs

        return R()


@pytest.mark.asyncio
async def test_canonicalize_flags_low_confidence(db_session: AsyncSession) -> None:
    router = FakeRouter()
    submission_id = uuid4()
    items = [{"id": submission_id, "raw_text": "متن", "language": "fa", "user_id": "u"}]
    candidates = await canonicalize_batch(session=db_session, submissions=items, llm_router=router)  # type: ignore[arg-type]
    assert len(candidates) == 1
    assert "low_confidence" in candidates[0].ambiguity_flags


@pytest.mark.asyncio
async def test_embedding_store_and_scheduler_smoke(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    user = await create_user(
        db_session, UserCreate(email=f"{uuid4()}@example.com", locale="fa", messaging_account_ref=str(uuid4()))
    )
    submission_row = await create_submission(
        db_session,
        SubmissionCreate(user_id=user.id, raw_text="text", language="fa", hash="c" * 64),
    )
    submission = await create_policy_candidate(
        db_session,
        PolicyCandidateCreate(
            submission_id=submission_row.id,
            title="Policy",
            domain=PolicyDomain.OTHER,
            summary="Summary",
            stance="neutral",
            policy_topic="test-topic",
            policy_key="test-policy",
            entities=[],
            confidence=1.0,
            ambiguity_flags=[],
            model_version="m",
            prompt_version="p",
        ),
    )
    count = await compute_and_store_embeddings(
        session=db_session, candidates=[submission], llm_router=FakeRouter()  # type: ignore[arg-type]
    )
    assert count == 1
    assert prepare_text_for_embedding(title="A", summary="B") == "A\n\nB"

    # scheduler smoke path: no pending submissions should still complete.
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://collective:pw@localhost:5432/collective_will"
    )
    monkeypatch.setenv("APP_PUBLIC_BASE_URL", "https://collectivewill.org")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("EVOLUTION_API_KEY", "x")
    result = await run_pipeline(session=db_session, llm_router=FakeRouter())  # type: ignore[arg-type]
    assert result.processed_submissions >= 0


@pytest.mark.asyncio
async def test_create_voting_cycle_query(db_session: AsyncSession) -> None:
    cycle = await create_voting_cycle(
        db_session,
        VotingCycleCreate(
            started_at=datetime.now(UTC),
            ends_at=datetime.now(UTC) + timedelta(days=1),
            status="active",
            cluster_ids=[],
            results=None,
            total_voters=0,
        ),
    )
    assert cycle.status == "active"


@pytest.mark.asyncio
async def test_run_pipeline_populates_cycle_cluster_ids(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIN_CLUSTER_SIZE", "2")
    get_settings.cache_clear()

    user = await create_user(
        db_session, UserCreate(email=f"{uuid4()}@example.com", locale="fa", messaging_account_ref=str(uuid4()))
    )
    user.email_verified = True
    user.messaging_verified = True
    user.messaging_account_age = datetime.now(UTC) - timedelta(hours=72)

    for idx in range(10):
        await create_submission(
            db_session,
            SubmissionCreate(user_id=user.id, raw_text=f"text-{idx}", language="fa", hash=("c" * 62) + f"{idx:02d}"),
        )
    await db_session.commit()

    result = await run_pipeline(session=db_session, llm_router=FakeRouter())  # type: ignore[arg-type]
    assert result.created_clusters >= 1

    cycle = (
        await db_session.execute(select(VotingCycle).order_by(VotingCycle.started_at.desc()))
    ).scalars().first()
    assert cycle is not None
    clusters = (await db_session.execute(select(Cluster).where(Cluster.cycle_id == cycle.id))).scalars().all()
    cluster_ids = {cluster.id for cluster in clusters}
    assert cluster_ids
    assert set(cycle.cluster_ids) == cluster_ids


@pytest.mark.asyncio
async def test_run_pipeline_uses_real_endorsement_count_path(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIN_CLUSTER_SIZE", "2")
    get_settings.cache_clear()

    user = await create_user(
        db_session, UserCreate(email=f"{uuid4()}@example.com", locale="fa", messaging_account_ref=str(uuid4()))
    )
    user.email_verified = True
    user.messaging_verified = True
    user.messaging_account_age = datetime.now(UTC) - timedelta(hours=72)

    for idx in range(10):
        await create_submission(
            db_session,
            SubmissionCreate(user_id=user.id, raw_text=f"text-{idx}", language="fa", hash=("d" * 62) + f"{idx:02d}"),
        )
    await db_session.commit()

    with patch("src.scheduler.main.count_cluster_endorsements", new_callable=AsyncMock, return_value=5) as mock_count:
        result = await run_pipeline(session=db_session, llm_router=FakeRouter())  # type: ignore[arg-type]
        assert result.created_clusters >= 1
        assert result.qualified_clusters >= 1
        assert mock_count.await_count >= 1
