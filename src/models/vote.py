from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.connection import Base

if TYPE_CHECKING:
    from src.models.cluster import Cluster
    from src.models.user import User


class VotingCycle(Base):
    __tablename__ = "voting_cycles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    cluster_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    results: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    total_voters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_log_id: Mapped[int | None] = mapped_column(nullable=True)

    votes: Mapped[list[Vote]] = relationship(back_populates="cycle")
    clusters: Mapped[list[Cluster]] = relationship(back_populates="cycle")

    def to_schema(self) -> VotingCycleRead:
        return VotingCycleRead.from_orm_model(self)


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    cycle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("voting_cycles.id"), nullable=False, index=True
    )
    approved_cluster_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    selections: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    evidence_log_id: Mapped[int | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(back_populates="votes")
    cycle: Mapped[VotingCycle] = relationship(back_populates="votes")

    def to_schema(self) -> VoteRead:
        return VoteRead.from_orm_model(self)


class VoteCreate(BaseModel):
    user_id: UUID
    cycle_id: UUID
    approved_cluster_ids: list[UUID] = Field(default_factory=list)
    selections: list[dict[str, Any]] | None = None


class VoteRead(BaseModel):
    id: UUID
    user_id: UUID
    cycle_id: UUID
    approved_cluster_ids: list[UUID]
    selections: list[dict[str, Any]] | None
    created_at: datetime
    evidence_log_id: int | None

    @classmethod
    def from_orm_model(cls, db_vote: Vote) -> VoteRead:
        return cls(
            id=db_vote.id,
            user_id=db_vote.user_id,
            cycle_id=db_vote.cycle_id,
            approved_cluster_ids=list(db_vote.approved_cluster_ids),
            selections=db_vote.selections,
            created_at=db_vote.created_at,
            evidence_log_id=db_vote.evidence_log_id,
        )


class VotingCycleCreate(BaseModel):
    started_at: datetime
    ends_at: datetime
    status: str = Field(default="active", pattern="^(active|closed|tallied)$")
    cluster_ids: list[UUID] = Field(default_factory=list)
    results: list[dict[str, Any]] | None = None
    total_voters: int = 0


class VotingCycleRead(BaseModel):
    id: UUID
    started_at: datetime
    ends_at: datetime
    status: str
    cluster_ids: list[UUID]
    results: list[dict[str, Any]] | None
    total_voters: int
    evidence_log_id: int | None

    @classmethod
    def from_orm_model(cls, db_cycle: VotingCycle) -> VotingCycleRead:
        return cls(
            id=db_cycle.id,
            started_at=db_cycle.started_at,
            ends_at=db_cycle.ends_at,
            status=db_cycle.status,
            cluster_ids=list(db_cycle.cluster_ids),
            results=db_cycle.results,
            total_voters=db_cycle.total_voters,
            evidence_log_id=db_cycle.evidence_log_id,
        )
