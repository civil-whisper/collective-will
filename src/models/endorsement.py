from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.connection import Base

if TYPE_CHECKING:
    from src.models.cluster import Cluster
    from src.models.user import User


class PolicyEndorsement(Base):
    __tablename__ = "policy_endorsements"
    __table_args__ = (UniqueConstraint("user_id", "cluster_id", name="uq_endorsement_user_cluster"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    cluster_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clusters.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    evidence_log_id: Mapped[int | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(back_populates="endorsements")
    cluster: Mapped[Cluster] = relationship(back_populates="endorsements")

    def to_schema(self) -> PolicyEndorsementRead:
        return PolicyEndorsementRead.from_orm_model(self)


class PolicyEndorsementCreate(BaseModel):
    user_id: UUID
    cluster_id: UUID


class PolicyEndorsementRead(BaseModel):
    id: UUID
    user_id: UUID
    cluster_id: UUID
    created_at: datetime
    evidence_log_id: int | None

    @classmethod
    def from_orm_model(cls, db_endorsement: PolicyEndorsement) -> PolicyEndorsementRead:
        return cls(
            id=db_endorsement.id,
            user_id=db_endorsement.user_id,
            cluster_id=db_endorsement.cluster_id,
            created_at=db_endorsement.created_at,
            evidence_log_id=db_endorsement.evidence_log_id,
        )
