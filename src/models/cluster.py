from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.connection import Base
from src.models.submission import PolicyDomain

if TYPE_CHECKING:
    from src.models.endorsement import PolicyEndorsement
    from src.models.policy_option import PolicyOption
    from src.models.vote import VotingCycle


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    cycle_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("voting_cycles.id"), nullable=True, index=True
    )
    policy_topic: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, server_default="unassigned"
    )
    policy_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, server_default="unassigned"
    )
    summary: Mapped[str] = mapped_column(String, nullable=False)
    summary_en: Mapped[str | None] = mapped_column(String, nullable=True)
    ballot_question: Mapped[str | None] = mapped_column(String, nullable=True)
    ballot_question_fa: Mapped[str | None] = mapped_column(String, nullable=True)
    domain: Mapped[PolicyDomain] = mapped_column(String(32), nullable=False)
    candidate_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    centroid_embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    cohesion_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    variance_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_resummarize: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clustering_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    approval_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_summarized_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    evidence_log_id: Mapped[int | None] = mapped_column(nullable=True)

    cycle: Mapped[VotingCycle | None] = relationship(back_populates="clusters")
    endorsements: Mapped[list[PolicyEndorsement]] = relationship(back_populates="cluster")
    options: Mapped[list[PolicyOption]] = relationship(
        back_populates="cluster", order_by="PolicyOption.position"
    )

    def to_schema(self) -> ClusterRead:
        return ClusterRead.from_orm_model(self)


class ClusterCreate(BaseModel):
    cycle_id: UUID | None = None
    policy_topic: str
    policy_key: str
    summary: str
    summary_en: str | None = None
    ballot_question: str | None = None
    ballot_question_fa: str | None = None
    domain: PolicyDomain
    candidate_ids: list[UUID]
    member_count: int = Field(ge=1)
    centroid_embedding: list[float] | None = None
    cohesion_score: float = 0.0
    variance_flag: bool = False
    needs_resummarize: bool = True
    run_id: str | None = None
    random_seed: int | None = None
    clustering_params: dict[str, Any] = Field(default_factory=dict)
    approval_count: int = 0
    last_summarized_count: int = 0


class ClusterRead(BaseModel):
    id: UUID
    cycle_id: UUID | None
    policy_topic: str
    policy_key: str
    summary: str
    summary_en: str | None
    ballot_question: str | None
    ballot_question_fa: str | None
    domain: PolicyDomain
    candidate_ids: list[UUID]
    member_count: int
    centroid_embedding: list[float] | None
    cohesion_score: float
    variance_flag: bool
    needs_resummarize: bool
    run_id: str | None
    random_seed: int | None
    clustering_params: dict[str, Any]
    approval_count: int
    last_summarized_count: int
    created_at: datetime
    evidence_log_id: int | None

    @classmethod
    def from_orm_model(cls, db_cluster: Cluster) -> ClusterRead:
        centroid: list[float] | None = None
        if db_cluster.centroid_embedding is not None:
            centroid = [float(v) for v in db_cluster.centroid_embedding]
        return cls(
            id=db_cluster.id,
            cycle_id=db_cluster.cycle_id,
            policy_topic=db_cluster.policy_topic,
            policy_key=db_cluster.policy_key,
            summary=db_cluster.summary,
            summary_en=db_cluster.summary_en,
            ballot_question=db_cluster.ballot_question,
            ballot_question_fa=db_cluster.ballot_question_fa,
            domain=db_cluster.domain,
            candidate_ids=list(db_cluster.candidate_ids),
            member_count=db_cluster.member_count,
            centroid_embedding=centroid,
            cohesion_score=db_cluster.cohesion_score,
            variance_flag=db_cluster.variance_flag,
            needs_resummarize=db_cluster.needs_resummarize,
            run_id=db_cluster.run_id,
            random_seed=db_cluster.random_seed,
            clustering_params=dict(db_cluster.clustering_params),
            approval_count=db_cluster.approval_count,
            last_summarized_count=db_cluster.last_summarized_count,
            created_at=db_cluster.created_at,
            evidence_log_id=db_cluster.evidence_log_id,
        )
