from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_db
from src.db.evidence import append_evidence
from src.handlers.disputes import resolve_submission_dispute
from src.models.submission import Submission
from src.models.user import User
from src.models.vote import Vote

router = APIRouter()


async def _require_user(
    session: AsyncSession,
    x_user_email: str | None,
) -> User:
    if not x_user_email:
        raise HTTPException(status_code=401, detail="missing user context")
    result = await session.execute(select(User).where(User.email == x_user_email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return user


@router.get("/dashboard/submissions")
async def list_submissions(
    session: AsyncSession = Depends(get_db),
    x_user_email: Annotated[str | None, Header()] = None,
) -> list[dict[str, str]]:
    user = await _require_user(session, x_user_email)
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
    session: AsyncSession = Depends(get_db),
    x_user_email: Annotated[str | None, Header()] = None,
) -> list[dict[str, str]]:
    user = await _require_user(session, x_user_email)
    result = await session.execute(select(Vote).where(Vote.user_id == user.id).order_by(Vote.created_at.desc()))
    rows = result.scalars().all()
    return [{"id": str(row.id), "cycle_id": str(row.cycle_id)} for row in rows]


@router.post("/dashboard/disputes/{submission_id}")
async def open_dispute(
    submission_id: str,
    session: AsyncSession = Depends(get_db),
    x_user_email: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    user = await _require_user(session, x_user_email)
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
