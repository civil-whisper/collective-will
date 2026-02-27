"""Add status column to clusters with partial unique index on policy_key.

Revision ID: 002_cluster_status
Revises: 001_initial_schema
Create Date: 2026-02-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_cluster_status"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clusters",
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
    )
    op.create_index("ix_clusters_status", "clusters", ["status"])

    op.drop_index("ix_clusters_policy_key", table_name="clusters")

    op.create_index(
        "uq_cluster_policy_key_open",
        "clusters",
        ["policy_key"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index("uq_cluster_policy_key_open", table_name="clusters")

    op.create_index("ix_clusters_policy_key", "clusters", ["policy_key"], unique=True)

    op.drop_index("ix_clusters_status", table_name="clusters")
    op.drop_column("clusters", "status")
