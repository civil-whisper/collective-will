from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

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
)
from src.handlers.voting import close_and_tally
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate, Submission
from src.models.vote import VotingCycle
from src.pipeline.agenda import build_agenda
from src.pipeline.canonicalize import canonicalize_batch, load_existing_policy_context
from src.pipeline.cluster import group_by_policy_key
from src.pipeline.embeddings import compute_and_store_embeddings
from src.pipeline.endorsement import generate_ballot_questions
from src.pipeline.llm import LLMRouter
from src.pipeline.normalize import normalize_policy_keys
from src.pipeline.options import generate_policy_options

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
            expired_result = await session.execute(
                select(VotingCycle)
                .where(VotingCycle.status == "active")
                .where(VotingCycle.ends_at <= datetime.now(UTC))
            )
            for cycle in expired_result.scalars().all():
                logger.info(
                    "Auto-closing expired voting cycle %s",
                    cycle.id,
                    extra={"event_type": "scheduler.cycle.auto_closed"},
                )
                await close_and_tally(session=session, cycle=cycle)

            ready_result = await session.execute(
                select(Submission)
                .where(Submission.status.in_(["canonicalized", "pending"]))
                .options(selectinload(Submission.candidates), selectinload(Submission.user))
                .order_by(Submission.created_at.asc())
            )
            submissions = list(ready_result.scalars().all())
            result.processed_submissions = len(submissions)
            if not submissions:
                await _run_daily_anchoring(session=session, router=router)
                return result

            policy_context = await load_existing_policy_context(session)

            pending_subs = [s for s in submissions if s.status == "pending"]
            if pending_subs:
                payloads = [
                    {"id": s.id, "raw_text": s.raw_text, "language": s.language}
                    for s in pending_subs
                ]
                candidate_creates = await canonicalize_batch(
                    session=session, submissions=payloads,
                    llm_router=router, policy_context=policy_context,
                )
                canonicalized_sub_ids = {data.submission_id for data in candidate_creates}
                for data in candidate_creates:
                    db_candidate = await create_policy_candidate(session, data)
                    await session.refresh(db_candidate)
                await session.flush()
                for sub in pending_subs:
                    await session.refresh(sub, attribute_names=["candidates"])
                    if sub.id in canonicalized_sub_ids:
                        sub.user.contribution_count += 1

            db_candidates: list[PolicyCandidate] = []
            for sub in submissions:
                db_candidates.extend(sub.candidates)
            result.created_candidates = len(db_candidates)

            needs_embed = [c for c in db_candidates if c.embedding is None]
            if needs_embed:
                await compute_and_store_embeddings(
                    session=session, candidates=needs_embed, llm_router=router,
                )

            groups = group_by_policy_key(candidates=db_candidates)
            db_clusters: list[Cluster] = []
            for policy_key, members in groups.items():
                cluster = await _find_or_create_cluster(
                    session=session, policy_key=policy_key, members=members,
                )
                db_clusters.append(cluster)
            result.created_clusters = len(db_clusters)

            merges = await normalize_policy_keys(session=session, llm_router=router)
            if merges:
                logger.info(
                    "Key normalization merged %d groups", len(merges),
                    extra={"event_type": "scheduler.normalization.completed"},
                )

            all_clusters_result = await session.execute(
                select(Cluster).where(Cluster.policy_key != "unassigned")
            )
            all_clusters = list(all_clusters_result.scalars().all())
            all_candidate_ids = {cid for cl in all_clusters for cid in cl.candidate_ids}
            all_candidates_result = await session.execute(
                select(PolicyCandidate).where(PolicyCandidate.id.in_(all_candidate_ids))
            )
            candidates_by_id = {
                c.id: c for c in all_candidates_result.scalars().all()
            }

            needs_ballot = [c for c in all_clusters if c.needs_resummarize]
            if needs_ballot:
                await generate_ballot_questions(
                    session=session, clusters=needs_ballot,
                    candidates_by_id=candidates_by_id, llm_router=router,
                )

            qualified_clusters = [
                c for c in all_clusters
                if c.ballot_question and not c.needs_resummarize
            ]
            clusters_needing_options = [
                c for c in qualified_clusters
                if not await _has_options(session, c.id)
            ]
            if clusters_needing_options:
                await generate_policy_options(
                    session=session, clusters=clusters_needing_options,
                    candidates_by_id=candidates_by_id, llm_router=router,
                )

            endorsement_counts = {
                str(c.id): await count_cluster_endorsements(session, c.id)
                for c in all_clusters
            }
            agenda_items = build_agenda(
                clusters=all_clusters,
                endorsement_counts=endorsement_counts,
                min_support=settings.min_preballot_endorsements,
            )
            result.qualified_clusters = sum(
                1 for item in agenda_items if item.qualifies
            )

            for submission in submissions:
                submission.status = "processed"
            await session.commit()

            logger.info(
                "Pipeline run completed: %d submissions, %d candidates, %d clusters",
                result.processed_submissions,
                result.created_candidates,
                result.created_clusters,
                extra={
                    "event_type": "scheduler.pipeline.completed",
                    "ops_payload": {
                        "processed_submissions": result.processed_submissions,
                        "created_candidates": result.created_candidates,
                        "created_clusters": result.created_clusters,
                        "qualified_clusters": result.qualified_clusters,
                    },
                },
            )

            await _run_daily_anchoring(session=session, router=router)
            return result
        except Exception as exc:  # pragma: no cover
            await session.rollback()
            logger.exception(
                "Pipeline run failed: %s",
                exc,
                extra={
                    "event_type": "scheduler.pipeline.error",
                    "ops_payload": {
                        "processed_submissions": result.processed_submissions,
                        "created_candidates": result.created_candidates,
                        "created_clusters": result.created_clusters,
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                    },
                },
            )
            result.errors.append(str(exc))
            return result


async def _find_or_create_cluster(
    *,
    session: AsyncSession,
    policy_key: str,
    members: list[PolicyCandidate],
) -> Cluster:
    """Find an existing cluster by policy_key, or create a new one."""
    from src.models.cluster import ClusterCreate

    result = await session.execute(
        select(Cluster).where(Cluster.policy_key == policy_key)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        new_ids = set(existing.candidate_ids) | {m.id for m in members}
        old_count = existing.member_count
        existing.candidate_ids = list(new_ids)
        existing.member_count = len(new_ids)
        growth = (existing.member_count - old_count) / max(old_count, 1)
        settings = get_settings()
        if growth >= settings.resummarize_growth_threshold:
            existing.needs_resummarize = True
        await session.flush()
        return existing

    topic = members[0].policy_topic if members else "unassigned"

    data = ClusterCreate(
        policy_topic=topic,
        policy_key=policy_key,
        summary=f"New policy discussion: {policy_key}",
        candidate_ids=[m.id for m in members],
        member_count=len(members),
        needs_resummarize=True,
    )
    db_cluster = await create_cluster(session, data)
    return db_cluster


async def _has_options(session: AsyncSession, cluster_id: UUID) -> bool:
    """Check if a cluster already has generated policy options."""
    from src.models.policy_option import PolicyOption

    result = await session.execute(
        select(PolicyOption.id).where(PolicyOption.cluster_id == cluster_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _run_daily_anchoring(*, session: AsyncSession, router: LLMRouter) -> None:
    settings = get_settings()
    root = await compute_daily_merkle_root(session, datetime.now(UTC).date())
    if root is None:
        return
    await publish_daily_merkle_root(root, datetime.now(UTC).date(), settings, session=session)


async def _count_unprocessed(session: AsyncSession) -> int:
    from sqlalchemy import func

    result = await session.execute(
        select(func.count())
        .select_from(Submission)
        .where(Submission.status.in_(["canonicalized", "pending"]))
    )
    return result.scalar_one()


async def scheduler_loop(
    *,
    session_factory,
    interval_hours: float,
    min_interval_hours: float,
    batch_threshold: int = 10,
    poll_seconds: float = 60.0,
) -> None:  # type: ignore[no-untyped-def]
    max_wait = max(interval_hours, min_interval_hours) * 3600

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

        elapsed = 0.0
        while elapsed < max_wait:
            await asyncio.sleep(poll_seconds)
            elapsed += poll_seconds
            async with session_factory() as session:
                count = await _count_unprocessed(session)
            if count >= batch_threshold:
                logger.info(
                    "Batch threshold reached (%d >= %d), triggering pipeline",
                    count,
                    batch_threshold,
                    extra={"event_type": "scheduler.threshold_trigger"},
                )
                break
