"""Add policy_options table, Vote.selections, User.bot_state_data for per-policy voting.

Revision ID: 005_per_policy_voting
Revises: 004_add_user_bot_state
Create Date: 2026-02-24 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005_per_policy_voting"
down_revision = "004_add_user_bot_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clusters.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("label_en", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("evidence_log_id", sa.BigInteger(), nullable=True),
    )

    op.add_column("votes", sa.Column("selections", postgresql.JSONB(), nullable=True))
    op.add_column("users", sa.Column("bot_state_data", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "bot_state_data")
    op.drop_column("votes", "selections")
    op.drop_table("policy_options")
