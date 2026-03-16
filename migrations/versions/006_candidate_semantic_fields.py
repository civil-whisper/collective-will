"""Add semantic fields and ballot readiness to policy candidates.

Revision ID: 006_candidate_semantic_fields
Revises: 005_enrollment_audio
Create Date: 2026-03-15 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_candidate_semantic_fields"
down_revision = "005_enrollment_audio"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policy_candidates",
        sa.Column("actor_scope", sa.String(length=64), nullable=False, server_default="unclear"),
    )
    op.add_column(
        "policy_candidates",
        sa.Column("action_mechanism", sa.String(length=64), nullable=False, server_default="unclear"),
    )
    op.add_column(
        "policy_candidates",
        sa.Column("target_scope", sa.String(length=64), nullable=False, server_default="unclear"),
    )
    op.add_column(
        "policy_candidates",
        sa.Column("ballot_readiness", sa.String(length=32), nullable=False, server_default="discussion_only"),
    )
    op.add_column(
        "policy_candidates",
        sa.Column("ballot_readiness_reason", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("policy_candidates", "ballot_readiness_reason")
    op.drop_column("policy_candidates", "ballot_readiness")
    op.drop_column("policy_candidates", "target_scope")
    op.drop_column("policy_candidates", "action_mechanism")
    op.drop_column("policy_candidates", "actor_scope")
