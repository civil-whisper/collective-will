"""Widen scheduler_heartbeat.detail from VARCHAR(256) to TEXT for full error context.

Revision ID: 006_heartbeat_detail_text
Revises: 005_per_policy_voting
Create Date: 2026-02-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_heartbeat_detail_text"
down_revision = "005_per_policy_voting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "scheduler_heartbeat",
        "detail",
        existing_type=sa.String(length=256),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "scheduler_heartbeat",
        "detail",
        existing_type=sa.Text(),
        type_=sa.String(length=256),
        existing_nullable=True,
    )
