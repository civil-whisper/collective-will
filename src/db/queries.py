from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cluster import Cluster, ClusterCreate
from src.models.endorsement import PolicyEndorsement, PolicyEndorsementCreate
from src.models.submission import (
    PolicyCandidate,
    PolicyCandidateCreate,
    Submission,
    SubmissionCreate,
)
from src.models.user import User, UserCreate
from src.models.vote import Vote, VoteCreate, VotingCycle, VotingCycleCreate


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(
        email=data.email,
        locale=data.locale,
        messaging_account_ref=data.messaging_account_ref,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_messaging_ref(session: AsyncSession, ref: str) -> User | None:
    result = await session.execute(select(User).where(User.messaging_account_ref == ref))
    return result.scalar_one_or_none()


async def create_submission(session: AsyncSession, data: SubmissionCreate) -> Submission:
    submission = Submission(
        user_id=data.user_id,
        raw_text=data.raw_text,
        language=data.language,
        hash=data.hash,
    )
    session.add(submission)
    await session.flush()
    await session.refresh(submission)
    return submission


async def get_submissions_by_user(session: AsyncSession, user_id: UUID) -> list[Submission]:
    result = await session.execute(
        select(Submission).where(Submission.user_id == user_id).order_by(Submission.created_at.desc())
    )
    return list(result.scalars().all())


async def create_policy_candidate(
    session: AsyncSession, data: PolicyCandidateCreate
) -> PolicyCandidate:
    candidate = PolicyCandidate(
        submission_id=data.submission_id,
        title=data.title,
        title_en=data.title_en,
        domain=data.domain,
        summary=data.summary,
        summary_en=data.summary_en,
        stance=data.stance,
        entities=data.entities,
        embedding=data.embedding,
        confidence=data.confidence,
        ambiguity_flags=data.ambiguity_flags,
        model_version=data.model_version,
        prompt_version=data.prompt_version,
    )
    session.add(candidate)
    await session.flush()
    await session.refresh(candidate)
    return candidate


async def create_cluster(session: AsyncSession, data: ClusterCreate) -> Cluster:
    cluster = Cluster(
        cycle_id=data.cycle_id,
        summary=data.summary,
        summary_en=data.summary_en,
        domain=data.domain,
        candidate_ids=data.candidate_ids,
        member_count=data.member_count,
        centroid_embedding=data.centroid_embedding,
        cohesion_score=data.cohesion_score,
        variance_flag=data.variance_flag,
        run_id=data.run_id,
        random_seed=data.random_seed,
        clustering_params=data.clustering_params,
        approval_count=data.approval_count,
    )
    session.add(cluster)
    await session.flush()
    await session.refresh(cluster)
    return cluster


async def create_policy_endorsement(
    session: AsyncSession, data: PolicyEndorsementCreate
) -> PolicyEndorsement:
    endorsement = PolicyEndorsement(user_id=data.user_id, cluster_id=data.cluster_id)
    session.add(endorsement)
    await session.flush()
    await session.refresh(endorsement)
    return endorsement


async def count_cluster_endorsements(session: AsyncSession, cluster_id: UUID) -> int:
    result = await session.execute(
        select(func.count(PolicyEndorsement.id)).where(PolicyEndorsement.cluster_id == cluster_id)
    )
    return int(result.scalar_one())


async def create_vote(session: AsyncSession, data: VoteCreate) -> Vote:
    vote = Vote(
        user_id=data.user_id,
        cycle_id=data.cycle_id,
        approved_cluster_ids=data.approved_cluster_ids,
    )
    session.add(vote)
    await session.flush()
    await session.refresh(vote)
    return vote


async def count_votes_for_cluster(session: AsyncSession, cycle_id: UUID, cluster_id: UUID) -> int:
    result = await session.execute(
        select(func.count(Vote.id)).where(
            Vote.cycle_id == cycle_id,
            Vote.approved_cluster_ids.contains([cluster_id]),
        )
    )
    return int(result.scalar_one())


async def create_voting_cycle(session: AsyncSession, data: VotingCycleCreate) -> VotingCycle:
    cycle = VotingCycle(
        started_at=data.started_at,
        ends_at=data.ends_at,
        status=data.status,
        cluster_ids=data.cluster_ids,
        results=data.results,
        total_voters=data.total_voters,
    )
    session.add(cycle)
    await session.flush()
    await session.refresh(cycle)
    return cycle
