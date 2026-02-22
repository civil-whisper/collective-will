from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.anchoring import compute_daily_merkle_root, publish_daily_merkle_root
from src.db.queries import create_cluster, create_policy_candidate, create_voting_cycle
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate, Submission
from src.models.vote import VotingCycleCreate
from src.pipeline.agenda import build_agenda
from src.pipeline.canonicalize import canonicalize_batch
from src.pipeline.cluster import run_clustering
from src.pipeline.embeddings import compute_and_store_embeddings
from src.pipeline.llm import LLMRouter
from src.pipeline.summarize import summarize_clusters

PIPELINE_LOCK = asyncio.Lock()


@dataclass(slots=True)
class PipelineResult:
    processed_submissions: int = 0
    created_candidates: int = 0
    created_clusters: int = 0
    qualified_clusters: int = 0
    errors: list[str] = field(default_factory=list)


async def run_pipeline(*, session: AsyncSession, llm_router: LLMRouter | None = None) -> PipelineResult:
    if PIPELINE_LOCK.locked():
        return PipelineResult(errors=["pipeline already running"])

    settings = get_settings()
    router = llm_router or LLMRouter(settings=settings)
    result = PipelineResult()
    async with PIPELINE_LOCK:
        try:
            pending_result = await session.execute(
                select(Submission).where(Submission.status == "pending").order_by(Submission.created_at.asc())
            )
            submissions = list(pending_result.scalars().all())
            result.processed_submissions = len(submissions)
            if not submissions:
                await _run_daily_anchoring(session=session, router=router)
                return result

            payloads = [{"id": item.id, "raw_text": item.raw_text, "language": item.language} for item in submissions]
            candidate_creates = await canonicalize_batch(
                session=session, submissions=payloads, llm_router=router
            )
            db_candidates: list[PolicyCandidate] = []
            for data in candidate_creates:
                db_candidate = await create_policy_candidate(session, data)
                db_candidates.append(db_candidate)
            result.created_candidates = len(db_candidates)

            await compute_and_store_embeddings(session=session, candidates=db_candidates, llm_router=router)

            cycle = await create_voting_cycle(
                session,
                data=VotingCycleCreate(
                    started_at=datetime.now(UTC),
                    ends_at=datetime.now(UTC) + timedelta(days=7),
                    status="active",
                    cluster_ids=[],
                    results=None,
                    total_voters=0,
                ),
            )
            clustering = run_clustering(
                candidates=db_candidates,
                cycle_id=cycle.id,
                min_cluster_size=settings.min_preballot_endorsements,
                random_seed=7,
            )
            db_clusters: list[Cluster] = []
            for item in clustering.clusters:
                db_cluster = await create_cluster(session, item)
                db_clusters.append(db_cluster)
            result.created_clusters = len(db_clusters)

            candidates_by_id = {candidate.id: candidate for candidate in db_candidates}
            await summarize_clusters(
                session=session,
                clusters=db_clusters,
                candidates_by_id=candidates_by_id,
                llm_router=router,
            )

            endorsement_counts = {str(cluster.id): 0 for cluster in db_clusters}
            agenda_items = build_agenda(
                clusters=db_clusters,
                endorsement_counts=endorsement_counts,
                min_cluster_size=settings.min_preballot_endorsements,
                min_preballot_endorsements=settings.min_preballot_endorsements,
            )
            result.qualified_clusters = sum(1 for item in agenda_items if item.qualifies)

            for submission in submissions:
                submission.status = "processed"
            await session.commit()

            await _run_daily_anchoring(session=session, router=router)
            return result
        except Exception as exc:  # pragma: no cover
            await session.rollback()
            result.errors.append(str(exc))
            return result


async def _run_daily_anchoring(*, session: AsyncSession, router: LLMRouter) -> None:
    settings = get_settings()
    root = await compute_daily_merkle_root(session, datetime.now(UTC).date())
    if root is None:
        return
    await publish_daily_merkle_root(root, datetime.now(UTC).date(), settings, session=session)


async def scheduler_loop(*, session_factory, interval_hours: int = 6) -> None:  # type: ignore[no-untyped-def]
    while True:
        async with session_factory() as session:
            await run_pipeline(session=session)
        await asyncio.sleep(interval_hours * 3600)
