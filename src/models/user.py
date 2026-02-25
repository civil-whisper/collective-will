from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.connection import Base

if TYPE_CHECKING:
    from src.models.endorsement import PolicyEndorsement
    from src.models.submission import Submission
    from src.models.vote import Vote


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    messaging_platform: Mapped[str] = mapped_column(String(32), default="whatsapp", nullable=False)
    messaging_account_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    messaging_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    messaging_account_age: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    locale: Mapped[str] = mapped_column(String(2), default="fa", nullable=False)
    trust_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    contribution_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bot_state: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    bot_state_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)

    submissions: Mapped[list[Submission]] = relationship(back_populates="user")
    votes: Mapped[list[Vote]] = relationship(back_populates="user")
    endorsements: Mapped[list[PolicyEndorsement]] = relationship(back_populates="user")

    def to_schema(self) -> UserRead:
        return UserRead.from_orm_model(self)


class UserCreate(BaseModel):
    email: EmailStr
    locale: str = Field(default="fa", pattern="^(fa|en)$")
    messaging_account_ref: str


class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    email_verified: bool
    messaging_platform: str
    messaging_account_ref: str
    messaging_verified: bool
    messaging_account_age: datetime | None
    created_at: datetime
    last_active_at: datetime
    locale: str
    trust_score: float
    contribution_count: int
    is_anonymous: bool
    bot_state: str | None = None

    @classmethod
    def from_orm_model(cls, db_user: User) -> UserRead:
        return cls(
            id=db_user.id,
            email=db_user.email,
            email_verified=db_user.email_verified,
            messaging_platform=db_user.messaging_platform,
            messaging_account_ref=db_user.messaging_account_ref,
            messaging_verified=db_user.messaging_verified,
            messaging_account_age=db_user.messaging_account_age,
            created_at=db_user.created_at,
            last_active_at=db_user.last_active_at,
            locale=db_user.locale,
            trust_score=db_user.trust_score,
            contribution_count=db_user.contribution_count,
            is_anonymous=db_user.is_anonymous,
            bot_state=db_user.bot_state,
        )
