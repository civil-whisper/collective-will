from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.queries import (
    create_policy_candidate,
    create_submission,
    create_user,
    create_voting_cycle,
)
from src.models.submission import PolicyCandidateCreate, PolicyDomain, SubmissionCreate
from src.models.user import UserCreate
from src.models.vote import VotingCycleCreate
from src.pipeline.canonicalize import canonicalize_batch
from src.pipeline.embeddings import compute_and_store_embeddings, prepare_text_for_embedding
from src.pipeline.llm import LLMResponse
from src.scheduler import run_pipeline


class FakeRouter:
    async def complete(self, *, tier: str, prompt: str, timeout_s: float = 60.0, **kwargs: object) -> LLMResponse:
        return LLMResponse(
            text='{"title":"Policy","domain":"economy","summary":"s","stance":"unclear","entities":[],"confidence":0.5,"ambiguity_flags":[]}',
            model="claude-sonnet-latest",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        )

    async def embed(self, texts: list[str], timeout_s: float = 30.0):  # type: ignore[no-untyped-def]
        class R:
            vectors = [[0.2, 0.3] for _ in texts]

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
