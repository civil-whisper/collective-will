from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import get_settings
from src.db.anchoring import compute_daily_merkle_root, publish_daily_merkle_root
from src.db.heartbeat import upsert_heartbeat
from src.db.queries import (
    count_cluster_endorsements,
    create_cluster,
    create_policy_candidate,
    create_voting_cycle,
)
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate, Submission
from src.models.vote import VotingCycleCreate
from src.pipeline.agenda import build_agenda
from src.pipeline.canonicalize import canonicalize_batch
from src.pipeline.cluster import run_clustering
from src.pipeline.embeddings import compute_and_store_embeddings
from src.pipeline.llm import LLMRouter
from src.pipeline.summarize import summarize_clusters

logger = logging.getLogger(__name__)

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
            # Canonicalized submissions have candidates+embeddings ready; just need clustering.
            # Also pick up any "pending" submissions whose inline canonicalization failed (LLM outage fallback).
            ready_result = await session.execute(
                select(Submission)
                .where(Submission.status.in_(["canonicalized", "pending"]))
                .options(selectinload(Submission.candidates))
                .order_by(Submission.created_at.asc())
            )
            submissions = list(ready_result.scalars().all())
            result.processed_submissions = len(submissions)
            if not submissions:
                await _run_daily_anchoring(session=session, router=router)
                return result

            # Fallback: canonicalize + embed any "pending" submissions that missed inline processing
            pending_subs = [s for s in submissions if s.status == "pending"]
            if pending_subs:
                payloads = [{"id": s.id, "raw_text": s.raw_text, "language": s.language} for s in pending_subs]
                candidate_creates = await canonicalize_batch(
                    session=session, submissions=payloads, llm_router=router,
                )
                for data in candidate_creates:
                    db_candidate = await create_policy_candidate(session, data)
                    await session.refresh(db_candidate)
                await session.flush()
                # Re-fetch to pick up new candidates
                for sub in pending_subs:
                    await session.refresh(sub, attribute_names=["candidates"])

            # Gather all candidates from this batch
            db_candidates: list[PolicyCandidate] = []
            for sub in submissions:
                db_candidates.extend(sub.candidates)
            result.created_candidates = len(db_candidates)

            # Embed any candidates still missing embeddings (from batch fallback)
            needs_embed = [c for c in db_candidates if c.embedding is None]
            if needs_embed:
                await compute_and_store_embeddings(
                    session=session, candidates=needs_embed, llm_router=router,
                )

            cycle = await create_voting_cycle(
                session,
                data=VotingCycleCreate(
                    started_at=datetime.now(UTC),
                    ends_at=datetime.now(UTC) + timedelta(hours=settings.voting_cycle_hours),
                    status="active",
                    cluster_ids=[],
                    results=None,
                    total_voters=0,
                ),
            )
            clustering = run_clustering(
                candidates=db_candidates,
                cycle_id=cycle.id,
                min_cluster_size=settings.min_cluster_size,
                min_samples=settings.cluster_min_samples,
                random_seed=settings.cluster_random_seed,
            )
            db_clusters: list[Cluster] = []
            for item in clustering.clusters:
                db_cluster = await create_cluster(session, item)
                db_clusters.append(db_cluster)
            result.created_clusters = len(db_clusters)
            cycle.cluster_ids = [cluster.id for cluster in db_clusters]

            candidates_by_id = {candidate.id: candidate for candidate in db_candidates}
            await summarize_clusters(
                session=session,
                clusters=db_clusters,
                candidates_by_id=candidates_by_id,
                llm_router=router,
            )

            endorsement_counts = {
                str(cluster.id): await count_cluster_endorsements(session, cluster.id)
                for cluster in db_clusters
            }
            agenda_items = build_agenda(
                clusters=db_clusters,
                endorsement_counts=endorsement_counts,
                min_cluster_size=settings.min_cluster_size,
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
            tb = traceback.format_exc()
            logger.exception("Pipeline run failed: %s", exc)
            result.errors.append(f"{type(exc).__name__}: {exc}\n{tb}")
            return result


async def _run_daily_anchoring(*, session: AsyncSession, router: LLMRouter) -> None:
    settings = get_settings()
    root = await compute_daily_merkle_root(session, datetime.now(UTC).date())
    if root is None:
        return
    await publish_daily_merkle_root(root, datetime.now(UTC).date(), settings, session=session)


async def scheduler_loop(
    *,
    session_factory,
    interval_hours: float,
    min_interval_hours: float,
) -> None:  # type: ignore[no-untyped-def]
    while True:
        async with session_factory() as session:
            result = await run_pipeline(session=session)
        async with session_factory() as session:
            detail = (
                f"processed={result.processed_submissions} "
                f"candidates={result.created_candidates} "
                f"clusters={result.created_clusters}"
            )
            status = "error" if result.errors else "ok"
            if result.errors:
                detail += f" errors={result.errors}"
            await upsert_heartbeat(session, status=status, detail=detail)
        await asyncio.sleep(max(interval_hours, min_interval_hours) * 3600)
