from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.queries import (
    count_cluster_endorsements,
    count_votes_for_cluster,
    create_cluster,
    create_policy_candidate,
    create_policy_endorsement,
    create_submission,
    create_user,
    create_vote,
    create_voting_cycle,
    get_user_by_email,
    get_user_by_messaging_ref,
)
from src.models import (
    ClusterCreate,
    PolicyCandidateCreate,
    PolicyDomain,
    PolicyEndorsementCreate,
    SubmissionCreate,
    UserCreate,
    VoteCreate,
    VotingCycleCreate,
)
from src.models.user import User


async def _seed_user(session: AsyncSession) -> tuple[str, str]:
    email = f"user-{uuid4()}@example.com"
    ref = str(uuid4())
    await create_user(session, UserCreate(email=email, locale="fa", messaging_account_ref=ref))
    await session.commit()
    return email, ref


@pytest.mark.asyncio
async def test_user_create_and_lookup(db_session: AsyncSession) -> None:
    email, ref = await _seed_user(db_session)
    by_email = await get_user_by_email(db_session, email)
    by_ref = await get_user_by_messaging_ref(db_session, ref)

    assert by_email is not None
    assert by_ref is not None
    assert by_email.trust_score == 0.0
    assert by_email.to_schema().email == email
    assert await get_user_by_email(db_session, "missing@example.com") is None


def test_policy_domain_validation() -> None:
    assert PolicyDomain("economy") == PolicyDomain.ECONOMY
    with pytest.raises(ValueError):
        PolicyDomain("not_a_domain")


def test_schema_validation_errors() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="bad", locale="fa", messaging_account_ref="x")

    with pytest.raises(ValidationError):
        PolicyCandidateCreate(
            submission_id=uuid4(),
            title="bad",
            domain=PolicyDomain.OTHER,
            summary="s",
            stance="invalid",
            entities=[],
            confidence=2.0,
            ambiguity_flags=[],
            model_version="m",
            prompt_version="p",
        )


@pytest.mark.asyncio
async def test_submission_candidate_cluster_vote_endorsement_flow(db_session: AsyncSession) -> None:
    email, ref = await _seed_user(db_session)
    user = await get_user_by_email(db_session, email)
    assert user is not None
    assert user.messaging_account_ref == ref

    submission = await create_submission(
        db_session,
        SubmissionCreate(
            user_id=user.id,
            raw_text="متن تست",
            language="fa",
            hash="a" * 64,
        ),
    )
    candidate = await create_policy_candidate(
        db_session,
        PolicyCandidateCreate(
            submission_id=submission.id,
            title="Affordable Housing Expansion",
            domain=PolicyDomain.ECONOMY,
            summary="Build affordable housing in major cities.",
            stance="neutral",
            entities=["housing"],
            embedding=[0.1] * 1024,
            confidence=0.9,
            ambiguity_flags=[],
            model_version="model-a",
            prompt_version="prompt-a",
        ),
    )
    cycle = await create_voting_cycle(
        db_session,
        VotingCycleCreate(
            started_at=datetime.now(UTC),
            ends_at=datetime.now(UTC) + timedelta(days=2),
            status="active",
            cluster_ids=[],
            results=None,
            total_voters=0,
        ),
    )
    cluster = await create_cluster(
        db_session,
        ClusterCreate(
            cycle_id=cycle.id,
            summary="مسکن ارزان",
            domain=PolicyDomain.ECONOMY,
            candidate_ids=[candidate.id],
            member_count=1,
            centroid_embedding=[0.1] * 1024,
            cohesion_score=0.95,
            run_id="run-1",
            random_seed=7,
            clustering_params={"min_cluster_size": 5},
            approval_count=0,
        ),
    )
    endorsement = await create_policy_endorsement(
        db_session, PolicyEndorsementCreate(user_id=user.id, cluster_id=cluster.id)
    )
    vote = await create_vote(
        db_session, VoteCreate(user_id=user.id, cycle_id=cycle.id, approved_cluster_ids=[cluster.id])
    )
    await db_session.commit()

    assert endorsement.cluster_id == cluster.id
    assert vote.cycle_id == cycle.id
    assert candidate.stance in {"neutral", "unclear"}
    assert candidate.embedding is not None and len(candidate.embedding) == 1024

    unclear_candidate = await create_policy_candidate(
        db_session,
        PolicyCandidateCreate(
            submission_id=submission.id,
            title="Unclear Policy Intent",
            domain=PolicyDomain.OTHER,
            summary="This text is ambiguous.",
            stance="unclear",
            entities=[],
            confidence=0.4,
            ambiguity_flags=["low_confidence"],
            model_version="model-a",
            prompt_version="prompt-a",
        ),
    )
    assert unclear_candidate.stance == "unclear"

    assert await count_cluster_endorsements(db_session, cluster.id) == 1
    assert await count_votes_for_cluster(db_session, cycle.id, cluster.id) == 1

    assert submission.to_schema().raw_text == "متن تست"
    assert candidate.to_schema().domain == PolicyDomain.ECONOMY
    assert cluster.to_schema().member_count == 1
    assert vote.to_schema().approved_cluster_ids == [cluster.id]
    assert cycle.to_schema().status == "active"
    assert endorsement.to_schema().user_id == user.id


@pytest.mark.asyncio
async def test_foreign_keys_and_unique_constraints(db_session: AsyncSession) -> None:
    bad_submission = SubmissionCreate(
        user_id=uuid4(),
        raw_text="bad",
        language="fa",
        hash="b" * 64,
    )
    with pytest.raises(IntegrityError):
        await create_submission(db_session, bad_submission)
    await db_session.rollback()

    email, _ = await _seed_user(db_session)
    user = await get_user_by_email(db_session, email)
    assert user is not None

    cycle = await create_voting_cycle(
        db_session,
        VotingCycleCreate(
            started_at=datetime.now(UTC),
            ends_at=datetime.now(UTC) + timedelta(days=1),
            cluster_ids=[],
            status="active",
            results=None,
            total_voters=0,
        ),
    )
    cluster = await create_cluster(
        db_session,
        ClusterCreate(
            cycle_id=cycle.id,
            summary="Cluster",
            domain=PolicyDomain.OTHER,
            candidate_ids=[],
            member_count=1,
            centroid_embedding=[0.0] * 1024,
            cohesion_score=1.0,
            run_id="run-2",
            random_seed=1,
            clustering_params={},
            approval_count=0,
        ),
    )
    await create_policy_endorsement(db_session, PolicyEndorsementCreate(user_id=user.id, cluster_id=cluster.id))
    await db_session.commit()
    user_id = user.id
    with pytest.raises(IntegrityError):
        await create_policy_endorsement(db_session, PolicyEndorsementCreate(user_id=user_id, cluster_id=cluster.id))
    await db_session.rollback()

    result = await db_session.execute(select(User).where(User.id == user_id))
    loaded_user = result.scalar_one()
    assert loaded_user.to_schema().id == user_id
