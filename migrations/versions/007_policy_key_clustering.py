"""Add policy_topic and policy_key for LLM-driven policy clustering.

Replaces HDBSCAN-based clustering with context-aware LLM policy assignment.
- PolicyCandidate: add policy_topic, policy_key
- Cluster: add policy_topic, policy_key (unique), ballot_question fields,
  needs_resummarize, last_summarized_count; make cycle_id, run_id,
  random_seed nullable

Revision ID: 007
Revises: 006
"""

from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "policy_candidates",
        sa.Column("policy_topic", sa.String(255), nullable=False, server_default="unassigned"),
    )
    op.add_column(
        "policy_candidates",
        sa.Column("policy_key", sa.String(255), nullable=False, server_default="unassigned"),
    )
    op.create_index("ix_policy_candidates_policy_topic", "policy_candidates", ["policy_topic"])
    op.create_index("ix_policy_candidates_policy_key", "policy_candidates", ["policy_key"])

    op.add_column(
        "clusters",
        sa.Column("policy_topic", sa.String(255), nullable=False, server_default="unassigned"),
    )
    op.add_column(
        "clusters",
        sa.Column("policy_key", sa.String(255), nullable=False, server_default="unassigned"),
    )
    op.add_column("clusters", sa.Column("ballot_question", sa.String, nullable=True))
    op.add_column("clusters", sa.Column("ballot_question_fa", sa.String, nullable=True))
    op.add_column(
        "clusters",
        sa.Column("needs_resummarize", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "clusters",
        sa.Column("last_summarized_count", sa.Integer, nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_clusters_policy_topic", "clusters", ["policy_topic"])
    op.create_index("ix_clusters_policy_key", "clusters", ["policy_key"], unique=True)

    op.alter_column("clusters", "cycle_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column("clusters", "run_id", existing_type=sa.String(128), nullable=True)
    op.alter_column("clusters", "random_seed", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("clusters", "random_seed", existing_type=sa.Integer(), nullable=False)
    op.alter_column("clusters", "run_id", existing_type=sa.String(128), nullable=False)
    op.alter_column("clusters", "cycle_id", existing_type=sa.UUID(), nullable=False)

    op.drop_index("ix_clusters_policy_key", table_name="clusters")
    op.drop_index("ix_clusters_policy_topic", table_name="clusters")
    op.drop_column("clusters", "last_summarized_count")
    op.drop_column("clusters", "needs_resummarize")
    op.drop_column("clusters", "ballot_question_fa")
    op.drop_column("clusters", "ballot_question")
    op.drop_column("clusters", "policy_key")
    op.drop_column("clusters", "policy_topic")

    op.drop_index("ix_policy_candidates_policy_key", table_name="policy_candidates")
    op.drop_index("ix_policy_candidates_policy_topic", table_name="policy_candidates")
    op.drop_column("policy_candidates", "policy_key")
    op.drop_column("policy_candidates", "policy_topic")
