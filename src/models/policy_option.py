from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.connection import Base

if TYPE_CHECKING:
    from src.models.cluster import Cluster


class PolicyOption(Base):
    """LLM-generated stance option for a cluster/policy topic."""

    __tablename__ = "policy_options"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    cluster_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clusters.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    label_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(String, nullable=False)
    description_en: Mapped[str | None] = mapped_column(String, nullable=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    evidence_log_id: Mapped[int | None] = mapped_column(nullable=True)

    cluster: Mapped[Cluster] = relationship(back_populates="options")

    def to_schema(self) -> PolicyOptionRead:
        return PolicyOptionRead.from_orm_model(self)


class PolicyOptionCreate(BaseModel):
    cluster_id: UUID
    position: int = Field(ge=1)
    label: str = Field(min_length=1)
    label_en: str | None = None
    description: str
    description_en: str | None = None
    model_version: str


class PolicyOptionRead(BaseModel):
    id: UUID
    cluster_id: UUID
    position: int
    label: str
    label_en: str | None
    description: str
    description_en: str | None
    model_version: str
    created_at: datetime
    evidence_log_id: int | None

    @classmethod
    def from_orm_model(cls, db_option: PolicyOption) -> PolicyOptionRead:
        return cls(
            id=db_option.id,
            cluster_id=db_option.cluster_id,
            position=db_option.position,
            label=db_option.label,
            label_en=db_option.label_en,
            description=db_option.description,
            description_en=db_option.description_en,
            model_version=db_option.model_version,
            created_at=db_option.created_at,
            evidence_log_id=db_option.evidence_log_id,
        )
