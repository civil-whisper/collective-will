"""Initial schema (clean slate).

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-02-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("messaging_platform", sa.String(length=32), nullable=False, server_default="whatsapp"),
        sa.Column("messaging_account_ref", sa.String(length=64), nullable=False),
        sa.Column("messaging_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("messaging_account_age", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locale", sa.String(length=2), nullable=False, server_default="fa"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("contribution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bot_state", sa.String(length=32), nullable=True),
        sa.Column("bot_state_data", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_messaging_account_ref", "users", ["messaging_account_ref"], unique=True)

    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_text", sa.String(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_log_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"], unique=False)
    op.create_index("ix_submissions_hash", "submissions", ["hash"], unique=False)

    op.create_table(
        "voting_cycles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("cluster_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=True),
        sa.Column("total_voters", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_log_id", sa.BigInteger(), nullable=True),
    )

    op.create_table(
        "policy_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("stance", sa.String(length=16), nullable=False),
        sa.Column("policy_topic", sa.String(length=255), nullable=False, server_default="unassigned"),
        sa.Column("policy_key", sa.String(length=255), nullable=False, server_default="unassigned"),
        sa.Column("entities", postgresql.JSONB(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("ambiguity_flags", postgresql.JSONB(), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_log_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_policy_candidates_submission_id", "policy_candidates", ["submission_id"])
    op.create_index("ix_policy_candidates_policy_topic", "policy_candidates", ["policy_topic"])
    op.create_index("ix_policy_candidates_policy_key", "policy_candidates", ["policy_key"])

    op.create_table(
        "clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("policy_topic", sa.String(length=255), nullable=False, server_default="unassigned"),
        sa.Column("policy_key", sa.String(length=255), nullable=False, server_default="unassigned"),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("ballot_question", sa.String(), nullable=True),
        sa.Column("ballot_question_fa", sa.String(), nullable=True),
        sa.Column("candidate_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("approval_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("needs_resummarize", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_summarized_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_log_id", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_clusters_policy_topic", "clusters", ["policy_topic"])
    op.create_index("ix_clusters_policy_key", "clusters", ["policy_key"], unique=True)

    op.create_table(
        "policy_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("label_en", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("evidence_log_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["cluster_id"], ["clusters.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_policy_options_cluster_id", "policy_options", ["cluster_id"])

    op.create_table(
        "votes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approved_cluster_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("selections", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_log_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cycle_id"], ["voting_cycles.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_votes_user_id", "votes", ["user_id"])
    op.create_index("ix_votes_cycle_id", "votes", ["cycle_id"])

    op.create_table(
        "policy_endorsements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_log_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cluster_id"], ["clusters.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("user_id", "cluster_id", name="uq_endorsement_user_cluster"),
    )
    op.create_index("ix_policy_endorsements_user_id", "policy_endorsements", ["user_id"])
    op.create_index("ix_policy_endorsements_cluster_id", "policy_endorsements", ["cluster_id"])

    op.create_table(
        "sealed_account_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("platform_id", sa.String(length=256), nullable=False),
        sa.Column("account_ref", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform", "platform_id", name="uq_sealed_platform_id"),
    )
    op.create_index("ix_sealed_account_ref", "sealed_account_mappings", ["account_ref"], unique=True)

    op.create_table(
        "verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("token", sa.String(length=256), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_verification_tokens_token", "verification_tokens", ["token"], unique=True)
    op.create_index("ix_verification_tokens_email", "verification_tokens", ["email"])

    op.create_table(
        "scheduler_heartbeat",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
    )

    op.create_table(
        "evidence_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.Text(), nullable=False),
    )
    op.create_index("idx_evidence_hash", "evidence_log", ["hash"])
    op.create_index("idx_evidence_entity", "evidence_log", ["entity_type", "entity_id"])

    op.create_table(
        "daily_anchors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("merkle_root", sa.String(length=64), nullable=False),
        sa.Column("published_receipt", sa.String(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("day", name="uq_daily_anchors_day"),
    )
    op.create_index("ix_daily_anchors_day", "daily_anchors", ["day"], unique=True)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_evidence_prev_hash()
        RETURNS TRIGGER AS $$
        DECLARE
            last_hash TEXT;
        BEGIN
            SELECT hash INTO last_hash
            FROM evidence_log
            ORDER BY id DESC
            LIMIT 1;

            IF last_hash IS NULL THEN
                IF NEW.prev_hash <> 'genesis' THEN
                    RAISE EXCEPTION 'Invalid prev_hash for genesis entry';
                END IF;
            ELSE
                IF NEW.prev_hash <> last_hash THEN
                    RAISE EXCEPTION 'Invalid prev_hash chain link';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_validate_evidence_prev_hash
        BEFORE INSERT ON evidence_log
        FOR EACH ROW
        EXECUTE FUNCTION validate_evidence_prev_hash();
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON evidence_log FROM collective")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_validate_evidence_prev_hash ON evidence_log")
    op.execute("DROP FUNCTION IF EXISTS validate_evidence_prev_hash")

    op.drop_index("ix_daily_anchors_day", table_name="daily_anchors")
    op.drop_table("daily_anchors")

    op.drop_index("idx_evidence_entity", table_name="evidence_log")
    op.drop_index("idx_evidence_hash", table_name="evidence_log")
    op.drop_table("evidence_log")

    op.drop_table("scheduler_heartbeat")

    op.drop_index("ix_verification_tokens_email", table_name="verification_tokens")
    op.drop_index("ix_verification_tokens_token", table_name="verification_tokens")
    op.drop_table("verification_tokens")

    op.drop_index("ix_sealed_account_ref", table_name="sealed_account_mappings")
    op.drop_table("sealed_account_mappings")

    op.drop_index("ix_policy_endorsements_cluster_id", table_name="policy_endorsements")
    op.drop_index("ix_policy_endorsements_user_id", table_name="policy_endorsements")
    op.drop_table("policy_endorsements")

    op.drop_index("ix_votes_cycle_id", table_name="votes")
    op.drop_index("ix_votes_user_id", table_name="votes")
    op.drop_table("votes")

    op.drop_index("ix_policy_options_cluster_id", table_name="policy_options")
    op.drop_table("policy_options")

    op.drop_index("ix_clusters_policy_key", table_name="clusters")
    op.drop_index("ix_clusters_policy_topic", table_name="clusters")
    op.drop_table("clusters")

    op.drop_index("ix_policy_candidates_policy_key", table_name="policy_candidates")
    op.drop_index("ix_policy_candidates_policy_topic", table_name="policy_candidates")
    op.drop_index("ix_policy_candidates_submission_id", table_name="policy_candidates")
    op.drop_table("policy_candidates")

    op.drop_table("voting_cycles")

    op.drop_index("ix_submissions_hash", table_name="submissions")
    op.drop_index("ix_submissions_user_id", table_name="submissions")
    op.drop_table("submissions")

    op.drop_index("ix_users_messaging_account_ref", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.execute("DROP EXTENSION IF EXISTS vector")
