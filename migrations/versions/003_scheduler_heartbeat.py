"""Add scheduler_heartbeat table for ops health monitoring.

Revision ID: 003_scheduler_heartbeat
Revises: 002_staging_persistence
Create Date: 2026-02-23 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003_scheduler_heartbeat"
down_revision = "002_staging_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduler_heartbeat",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("scheduler_heartbeat")
