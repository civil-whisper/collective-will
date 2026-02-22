"""Add sealed_account_mappings and verification_tokens tables.

Revision ID: 002_staging_persistence
Revises: 001_initial_schema
Create Date: 2026-02-22 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002_staging_persistence"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sealed_account_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("platform_id", sa.String(length=256), nullable=False),
        sa.Column("account_ref", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform", "platform_id", name="uq_sealed_platform_id"),
    )
    op.create_index("ix_sealed_account_ref", "sealed_account_mappings", ["account_ref"], unique=True)

    op.create_table(
        "verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("token", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_verification_tokens_token", "verification_tokens", ["token"], unique=True)
    op.create_index("ix_verification_tokens_email", "verification_tokens", ["email"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_verification_tokens_email", table_name="verification_tokens")
    op.drop_index("ix_verification_tokens_token", table_name="verification_tokens")
    op.drop_table("verification_tokens")

    op.drop_index("ix_sealed_account_ref", table_name="sealed_account_mappings")
    op.drop_table("sealed_account_mappings")
