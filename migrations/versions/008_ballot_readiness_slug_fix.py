"""Normalize ballot_readiness slugs.

Revision ID: 008_ballot_readiness_slug_fix
Revises: 007_cluster_refinement_drafts
Create Date: 2026-03-15 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "008_ballot_readiness_slug_fix"
down_revision = "007_cluster_refinement_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE policy_candidates
        SET ballot_readiness = CASE ballot_readiness
            WHEN 'ballot_ready' THEN 'ballot-ready'
            WHEN 'needs_refinement' THEN 'needs-refinement'
            WHEN 'discussion_only' THEN 'discussion-only'
            ELSE ballot_readiness
        END
        """
    )
    op.execute(
        """
        ALTER TABLE policy_candidates
        ALTER COLUMN ballot_readiness SET DEFAULT 'discussion-only'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE policy_candidates
        SET ballot_readiness = CASE ballot_readiness
            WHEN 'ballot-ready' THEN 'ballot_ready'
            WHEN 'needs-refinement' THEN 'needs_refinement'
            WHEN 'discussion-only' THEN 'discussion_only'
            ELSE ballot_readiness
        END
        """
    )
    op.execute(
        """
        ALTER TABLE policy_candidates
        ALTER COLUMN ballot_readiness SET DEFAULT 'discussion_only'
        """
    )
