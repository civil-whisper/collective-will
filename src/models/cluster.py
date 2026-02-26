from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.connection import Base

if TYPE_CHECKING:
    from src.models.endorsement import PolicyEndorsement
    from src.models.policy_option import PolicyOption


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_topic: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, server_default="unassigned"
    )
    policy_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, server_default="unassigned"
    )
    summary: Mapped[str] = mapped_column(String, nullable=False)
    ballot_question: Mapped[str | None] = mapped_column(String, nullable=True)
    ballot_question_fa: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    needs_resummarize: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_summarized_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    evidence_log_id: Mapped[int | None] = mapped_column(nullable=True)

    endorsements: Mapped[list[PolicyEndorsement]] = relationship(back_populates="cluster")
    options: Mapped[list[PolicyOption]] = relationship(
        back_populates="cluster", order_by="PolicyOption.position"
    )

    def to_schema(self) -> ClusterRead:
        return ClusterRead.from_orm_model(self)


class ClusterCreate(BaseModel):
    policy_topic: str
    policy_key: str
    summary: str
    ballot_question: str | None = None
    ballot_question_fa: str | None = None
    candidate_ids: list[UUID]
    member_count: int = Field(ge=1)
    approval_count: int = 0
    needs_resummarize: bool = True
    last_summarized_count: int = 0


class ClusterRead(BaseModel):
    id: UUID
    policy_topic: str
    policy_key: str
    summary: str
    ballot_question: str | None
    ballot_question_fa: str | None
    candidate_ids: list[UUID]
    member_count: int
    approval_count: int
    needs_resummarize: bool
    last_summarized_count: int
    created_at: datetime
    evidence_log_id: int | None

    @classmethod
    def from_orm_model(cls, db_cluster: Cluster) -> ClusterRead:
        return cls(
            id=db_cluster.id,
            policy_topic=db_cluster.policy_topic,
            policy_key=db_cluster.policy_key,
            summary=db_cluster.summary,
            ballot_question=db_cluster.ballot_question,
            ballot_question_fa=db_cluster.ballot_question_fa,
            candidate_ids=list(db_cluster.candidate_ids),
            member_count=db_cluster.member_count,
            approval_count=db_cluster.approval_count,
            needs_resummarize=db_cluster.needs_resummarize,
            last_summarized_count=db_cluster.last_summarized_count,
            created_at=db_cluster.created_at,
            evidence_log_id=db_cluster.evidence_log_id,
        )
