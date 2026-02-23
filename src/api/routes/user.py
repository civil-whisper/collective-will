from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.authn import require_user_from_bearer
from src.db.connection import get_db
from src.db.evidence import append_evidence
from src.handlers.disputes import resolve_submission_dispute
from src.models.submission import Submission
from src.models.user import User
from src.models.vote import Vote

router = APIRouter()


@router.get("/dashboard/submissions")
async def list_submissions(
    user: Annotated[User, Depends(require_user_from_bearer)],
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, str]]:
    result = await session.execute(
        select(Submission).where(Submission.user_id == user.id).order_by(Submission.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        {"id": str(row.id), "raw_text": row.raw_text, "status": row.status, "hash": row.hash}
        for row in rows
    ]


@router.get("/dashboard/votes")
async def list_votes(
    user: Annotated[User, Depends(require_user_from_bearer)],
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    result = await session.execute(select(Vote).where(Vote.user_id == user.id).order_by(Vote.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": str(row.id),
            "cycle_id": str(row.cycle_id),
            "approved_cluster_ids": [str(cluster_id) for cluster_id in row.approved_cluster_ids],
        }
        for row in rows
    ]


@router.post("/dashboard/disputes/{submission_id}")
async def open_dispute(
    submission_id: str,
    user: Annotated[User, Depends(require_user_from_bearer)],
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        submission_uuid = UUID(submission_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid submission id") from exc
    result = await session.execute(
        select(Submission).where(Submission.id == submission_uuid, Submission.user_id == user.id)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="submission not found")

    await append_evidence(
        session=session,
        event_type="dispute_opened",
        entity_type="dispute",
        entity_id=submission.id,
        payload={"state": "dispute_open", "resolution_mode": "autonomous"},
    )
    await session.commit()
    await resolve_submission_dispute(session=session, submission=submission)
    return {"status": "under_automated_review"}
