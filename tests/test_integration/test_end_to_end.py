from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import verify_chain
from src.db.queries import create_user
from src.handlers.intake import process_submission
from src.models.submission import PolicyCandidate, Submission
from src.models.user import UserCreate
from src.scheduler import run_pipeline


class IntegrationRouter:
    async def complete(self, *, tier: str, prompt: str, timeout_s: float = 60.0, **kwargs: object):  # type: ignore[no-untyped-def]
        payload = (
            '{"title":"Water Access Policy","domain":"rights","summary":"Ensure water access",'
            '"stance":"support","entities":["water"],"confidence":0.9,"ambiguity_flags":[]}'
        )
        return type(
            "Completion",
            (),
            {
                "text": payload,
                "model": "claude-sonnet-latest",
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": 0.0,
            },
        )()

    async def embed(self, texts: list[str], timeout_s: float = 60.0):  # type: ignore[no-untyped-def]
        return type(
            "Embedding",
            (),
            {
                "vectors": [[0.01] * 1024 for _ in texts],
                "model": "text-embedding-3-large",
                "provider": "openai",
            },
        )()


@pytest.mark.asyncio
async def test_end_to_end_intake_pipeline_and_evidence(db_session: AsyncSession) -> None:
    user = await create_user(
        db_session, UserCreate(email=f"{uuid4()}@example.com", locale="fa", messaging_account_ref=str(uuid4()))
    )
    user.email_verified = True
    user.messaging_verified = True
    user.messaging_account_age = datetime.now(UTC) - timedelta(hours=72)
    await db_session.commit()

    submission, status = await process_submission(
        session=db_session,
        user=user,
        raw_text="کمبود آب آشامیدنی در استان",
        min_account_age_hours=48,
    )
    assert submission is not None
    assert status in {"accepted", "accepted_flagged"}

    result = await run_pipeline(session=db_session, llm_router=IntegrationRouter())  # type: ignore[arg-type]
    assert result.processed_submissions >= 1

    submission_rows = await db_session.execute(select(Submission))
    candidate_rows = await db_session.execute(select(PolicyCandidate))
    assert len(submission_rows.scalars().all()) >= 1
    assert len(candidate_rows.scalars().all()) >= 1

    valid, checked = await verify_chain(db_session)
    assert valid is True
    assert checked >= 1
