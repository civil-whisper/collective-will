from __future__ import annotations

import asyncio
import os
from functools import partial

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_TABLES = {
    "clusters",
    "daily_anchors",
    "enrollment_audio",
    "evidence_log",
    "ip_signup_log",
    "policy_candidates",
    "policy_endorsements",
    "policy_options",
    "scheduler_heartbeat",
    "sealed_account_mappings",
    "submissions",
    "users",
    "verification_tokens",
    "votes",
    "voting_cycles",
}


def _alembic_config(database_url: str) -> Config:
    cfg = Config("alembic.ini")
    os.environ["DATABASE_URL"] = database_url
    os.environ["APP_PUBLIC_BASE_URL"] = "https://collectivewill.org"
    os.environ["ANTHROPIC_API_KEY"] = "x"
    os.environ["OPENAI_API_KEY"] = "x"
    os.environ["DEEPSEEK_API_KEY"] = "x"
    os.environ["EVOLUTION_API_KEY"] = "x"
    from src.config import get_settings

    get_settings.cache_clear()
    return cfg


async def _run_alembic(fn: partial[None]) -> None:
    """Run an Alembic command in a thread (it calls asyncio.run() internally)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, fn)


@pytest.mark.asyncio
async def test_migration_upgrade_downgrade_roundtrip(test_database_url: str) -> None:
    cfg = _alembic_config(test_database_url)

    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
    await engine.dispose()

    await _run_alembic(partial(command.downgrade, cfg, "base"))
    await _run_alembic(partial(command.upgrade, cfg, "head"))

    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        version_rows = await conn.execute(text("SELECT version_num FROM alembic_version"))
        assert version_rows.scalar_one() == "001_initial_schema"

        table_rows = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public'"
            )
        )
        assert {row[0] for row in table_rows.fetchall()} == EXPECTED_TABLES

        trigger_rows = await conn.execute(
            text(
                "SELECT tgname FROM pg_trigger "
                "WHERE tgname='trg_validate_evidence_prev_hash'"
            )
        )
        assert trigger_rows.fetchone() is not None

        ext_rows = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
        assert ext_rows.fetchone() is not None

    await engine.dispose()
    await _run_alembic(partial(command.downgrade, cfg, "base"))

    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        remaining_tables = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public'"
            )
        )
        assert {row[0] for row in remaining_tables.fetchall()} == set()
    await engine.dispose()

    await _run_alembic(partial(command.upgrade, cfg, "head"))
