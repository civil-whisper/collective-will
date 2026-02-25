"""Add bot_state column to users table for Telegram inline-keyboard state machine.

Revision ID: 004_add_user_bot_state
Revises: 003_scheduler_heartbeat
Create Date: 2026-02-24 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_add_user_bot_state"
down_revision = "003_scheduler_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bot_state", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "bot_state")
