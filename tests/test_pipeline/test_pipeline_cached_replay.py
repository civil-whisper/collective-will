from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.analytics import clusters as analytics_clusters
from src.api.routes.analytics import evidence as analytics_evidence
from src.config import get_settings
from src.db.evidence import verify_chain
from src.db.queries import create_submission, create_user
from src.models.cluster import Cluster
from src.models.submission import SubmissionCreate
from src.models.user import UserCreate
from src.pipeline.llm import EmbeddingResult, LLMResponse
from src.scheduler import run_pipeline

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "pipeline_replay_fixture.json"


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class FixtureReplayRouter:
    def __init__(self, fixture: dict[str, object]) -> None:
        submissions = fixture.get("submissions", [])
        if not isinstance(submissions, list):
            raise ValueError("Fixture submissions must be a list")
        self._canonical_by_text: dict[str, dict[str, object]] = {}
        for item in submissions:
            if not isinstance(item, dict):
                continue
            raw_text = item.get("raw_text")
            canonical = item.get("canonical")
            if isinstance(raw_text, str) and isinstance(canonical, dict):
                self._canonical_by_text[raw_text] = canonical

    async def complete(
        self,
        *,
        tier: str,
        prompt: str,
        timeout_s: float = 60.0,
        **kwargs: object,
    ) -> LLMResponse:
        if tier == "canonicalization":
            raw_text = self._extract_raw_text(prompt)
            canonical = self._canonical_by_text.get(raw_text)
            if canonical is None:
                raise ValueError(f"No fixture canonicalization for text: {raw_text}")
            return LLMResponse(
                text=json.dumps(canonical, ensure_ascii=False),
                model="fixture-canonical-v1",
                input_tokens=10,
                output_tokens=8,
                cost_usd=0.0,
            )

        if tier == "english_reasoning":
            return LLMResponse(
                text="Cluster summary",
                model="fixture-summary-v1",
                input_tokens=10,
                output_tokens=8,
                cost_usd=0.0,
            )

        raise ValueError(f"Unsupported tier in fixture router: {tier}")

    async def embed(self, texts: list[str], timeout_s: float = 60.0) -> EmbeddingResult:
        vectors = [self._vector_for_text(text) for text in texts]
        return EmbeddingResult(vectors=vectors, model="fixture-embedding-v1", provider="fixture")

    @staticmethod
    def _extract_raw_text(prompt: str) -> str:
        marker = "Input: "
        start = prompt.rfind(marker)
        if start == -1:
            raise ValueError("Canonicalization prompt missing Input marker")
        payload = prompt[start + len(marker) :].strip()
        parsed = json.loads(payload)
        raw_text = parsed.get("raw_text")
        if not isinstance(raw_text, str):
            raise ValueError("Prompt payload missing raw_text")
        return raw_text

    @staticmethod
    def _vector_for_text(text: str) -> list[float]:
        import numpy as np

        if "Water" in text:
            center = 0.0
        elif "Tax" in text:
            center = 10.0
        else:
            center = 5.0
        rng = np.random.RandomState(hash(text) & 0x7FFFFFFF)
        return rng.normal(center, 0.1, 1024).tolist()


@pytest.mark.asyncio
async def test_cached_fixture_pipeline_replay(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIN_PREBALLOT_ENDORSEMENTS", "1")
    get_settings.cache_clear()

    fixture = _load_fixture()
    submissions_fixture = fixture.get("submissions")
    assert isinstance(submissions_fixture, list)
    assert len(submissions_fixture) >= 4

    user = await create_user(
        db_session, UserCreate(email=f"{uuid4()}@example.com", locale="fa", messaging_account_ref=str(uuid4()))
    )
    user.email_verified = True
    user.messaging_verified = True
    user.messaging_account_age = datetime.now(UTC) - timedelta(hours=72)

    for item in submissions_fixture:
        assert isinstance(item, dict)
        raw_text = item.get("raw_text")
        assert isinstance(raw_text, str)
        await create_submission(
            db_session,
            SubmissionCreate(
                user_id=user.id,
                raw_text=raw_text,
                language="fa",
                hash=uuid4().hex + uuid4().hex,
            ),
        )
    await db_session.commit()

    router = FixtureReplayRouter(fixture)
    result = await run_pipeline(session=db_session, llm_router=router)  # type: ignore[arg-type]

    assert result.errors == []
    assert result.processed_submissions == len(submissions_fixture)
    assert result.created_candidates == len(submissions_fixture)
    assert result.created_clusters >= 2
    assert result.qualified_clusters >= 0

    clusters = (
        await db_session.execute(select(Cluster).where(Cluster.policy_key != "unassigned"))
    ).scalars().all()
    assert len(clusters) >= 2
    assert all(c.policy_key != "unassigned" for c in clusters)

    valid, checked = await verify_chain(db_session)
    assert valid is True
    assert checked > 0

    clusters_payload = await analytics_clusters(session=db_session)
    evidence_payload = await analytics_evidence(
        session=db_session, entity_id=None, event_type=None, page=1, per_page=200,
    )
    assert len(clusters_payload) == len(clusters)
    assert any(entry["event_type"] == "candidate_created" for entry in evidence_payload["entries"])
