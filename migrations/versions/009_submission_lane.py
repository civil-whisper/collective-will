"""Add submission_lane to policy_candidates and clusters.

Revision ID: 009_submission_lane
Revises: 008_ballot_readiness_slug_fix
Create Date: 2026-03-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009_submission_lane"
down_revision = "008_ballot_readiness_slug_fix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policy_candidates",
        sa.Column("submission_lane", sa.String(32), nullable=False, server_default="policy_proposal"),
    )
    op.create_index("ix_policy_candidates_submission_lane", "policy_candidates", ["submission_lane"])

    op.add_column(
        "clusters",
        sa.Column("submission_lane", sa.String(32), nullable=False, server_default="policy_proposal"),
    )
    op.create_index("ix_clusters_submission_lane", "clusters", ["submission_lane"])

    op.drop_index("uq_cluster_policy_key_open", table_name="clusters")
    op.create_index(
        "uq_cluster_policy_key_lane_open",
        "clusters",
        ["policy_key", "submission_lane"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_cluster_policy_key_lane_open", table_name="clusters")
    op.create_index(
        "uq_cluster_policy_key_open",
        "clusters",
        ["policy_key"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index("ix_clusters_submission_lane", table_name="clusters")
    op.drop_column("clusters", "submission_lane")
    op.drop_index("ix_policy_candidates_submission_lane", table_name="policy_candidates")
    op.drop_column("policy_candidates", "submission_lane")
