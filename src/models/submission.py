from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.connection import Base

if TYPE_CHECKING:
    from src.models.user import User


class PolicyDomain(StrEnum):
    GOVERNANCE = "governance"
    ECONOMY = "economy"
    RIGHTS = "rights"
    FOREIGN_POLICY = "foreign_policy"
    RELIGION = "religion"
    ETHNIC = "ethnic"
    JUSTICE = "justice"
    OTHER = "other"


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    evidence_log_id: Mapped[int | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(back_populates="submissions")
    candidates: Mapped[list[PolicyCandidate]] = relationship(back_populates="submission")

    def to_schema(self) -> SubmissionRead:
        return SubmissionRead.from_orm_model(self)


class PolicyCandidate(Base):
    __tablename__ = "policy_candidates"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    submission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("submissions.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain: Mapped[PolicyDomain] = mapped_column(nullable=False, default=PolicyDomain.OTHER)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    summary_en: Mapped[str | None] = mapped_column(String, nullable=True)
    stance: Mapped[str] = mapped_column(String(16), nullable=False)
    entities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ambiguity_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    evidence_log_id: Mapped[int | None] = mapped_column(nullable=True)

    submission: Mapped[Submission] = relationship(back_populates="candidates")

    def to_schema(self) -> PolicyCandidateRead:
        return PolicyCandidateRead.from_orm_model(self)


class SubmissionCreate(BaseModel):
    user_id: UUID
    raw_text: str
    language: str
    hash: str


class SubmissionRead(BaseModel):
    id: UUID
    user_id: UUID
    raw_text: str
    language: str
    status: str
    processed_at: datetime | None
    hash: str
    created_at: datetime
    evidence_log_id: int | None

    @classmethod
    def from_orm_model(cls, db_submission: Submission) -> SubmissionRead:
        return cls(
            id=db_submission.id,
            user_id=db_submission.user_id,
            raw_text=db_submission.raw_text,
            language=db_submission.language,
            status=db_submission.status,
            processed_at=db_submission.processed_at,
            hash=db_submission.hash,
            created_at=db_submission.created_at,
            evidence_log_id=db_submission.evidence_log_id,
        )


class PolicyCandidateCreate(BaseModel):
    submission_id: UUID
    title: str = Field(min_length=5)
    title_en: str | None = None
    domain: PolicyDomain
    summary: str
    summary_en: str | None = None
    stance: str = Field(pattern="^(support|oppose|neutral|unclear)$")
    entities: list[str]
    embedding: list[float] | None = None
    confidence: float = Field(ge=0, le=1)
    ambiguity_flags: list[str]
    model_version: str
    prompt_version: str


class PolicyCandidateRead(BaseModel):
    id: UUID
    submission_id: UUID
    title: str
    title_en: str | None
    domain: PolicyDomain
    summary: str
    summary_en: str | None
    stance: str
    entities: list[str]
    embedding: list[float] | None
    confidence: float
    ambiguity_flags: list[str]
    model_version: str
    prompt_version: str
    created_at: datetime
    evidence_log_id: int | None

    @classmethod
    def from_orm_model(cls, db_candidate: PolicyCandidate) -> PolicyCandidateRead:
        embedding: list[float] | None = None
        if db_candidate.embedding is not None:
            embedding = [float(v) for v in db_candidate.embedding]
        return cls(
            id=db_candidate.id,
            submission_id=db_candidate.submission_id,
            title=db_candidate.title,
            title_en=db_candidate.title_en,
            domain=db_candidate.domain,
            summary=db_candidate.summary,
            summary_en=db_candidate.summary_en,
            stance=db_candidate.stance,
            entities=list(db_candidate.entities),
            embedding=embedding,
            confidence=db_candidate.confidence,
            ambiguity_flags=list(db_candidate.ambiguity_flags),
            model_version=db_candidate.model_version,
            prompt_version=db_candidate.prompt_version,
            created_at=db_candidate.created_at,
            evidence_log_id=db_candidate.evidence_log_id,
        )


def candidate_embedding_payload(candidate: PolicyCandidate) -> dict[str, Any]:
    return {"title": candidate.title, "summary": candidate.summary}
