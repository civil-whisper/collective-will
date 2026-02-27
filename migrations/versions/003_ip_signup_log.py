"""Add ip_signup_log table for DB-backed IP rate limiting.

Revision ID: 003_ip_signup_log
Revises: 002_cluster_status
Create Date: 2026-02-27 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003_ip_signup_log"
down_revision = "002_cluster_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ip_signup_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("requester_ip", sa.String(45), nullable=False),
        sa.Column("email_domain", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Composite index for rate-window lookups: WHERE requester_ip = ? AND created_at >= ?
    op.create_index(
        "ix_ip_signup_log_ip_created_at",
        "ip_signup_log",
        ["requester_ip", "created_at"],
    )
    # Cleanup index for periodic pruning of old rows
    op.create_index(
        "ix_ip_signup_log_created_at",
        "ip_signup_log",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ip_signup_log_created_at", table_name="ip_signup_log")
    op.drop_index("ix_ip_signup_log_ip_created_at", table_name="ip_signup_log")
    op.drop_table("ip_signup_log")
