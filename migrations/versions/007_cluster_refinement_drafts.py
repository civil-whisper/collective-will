"""Add refinement draft fields to clusters.

Revision ID: 007_cluster_refinement_drafts
Revises: 006_candidate_semantic_fields
Create Date: 2026-03-15 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_cluster_refinement_drafts"
down_revision = "006_candidate_semantic_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clusters", sa.Column("refinement_draft", sa.String(), nullable=True))
    op.add_column("clusters", sa.Column("refinement_draft_fa", sa.String(), nullable=True))
    op.add_column("clusters", sa.Column("refinement_confidence", sa.Float(), nullable=True))
    op.add_column(
        "clusters",
        sa.Column("refinement_requires_clarification", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("clusters", sa.Column("refinement_notes", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("clusters", "refinement_notes")
    op.drop_column("clusters", "refinement_requires_clarification")
    op.drop_column("clusters", "refinement_confidence")
    op.drop_column("clusters", "refinement_draft_fa")
    op.drop_column("clusters", "refinement_draft")
