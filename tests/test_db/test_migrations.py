from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _alembic_config(database_url: str) -> Config:
    cfg = Config("alembic.ini")
    os.environ["DATABASE_URL"] = database_url
    os.environ["APP_PUBLIC_BASE_URL"] = "https://collectivewill.org"
    os.environ["ANTHROPIC_API_KEY"] = "x"
    os.environ["OPENAI_API_KEY"] = "x"
    os.environ["DEEPSEEK_API_KEY"] = "x"
    os.environ["EVOLUTION_API_KEY"] = "x"
    return cfg


@pytest.mark.asyncio
async def test_migration_upgrade_downgrade_roundtrip(test_database_url: str) -> None:
    cfg = _alembic_config(test_database_url)
    command.upgrade(cfg, "head")

    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        table_rows = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name IN "
                "('users','submissions','policy_candidates','voting_cycles','clusters','votes','evidence_log')"
            )
        )
        assert len(table_rows.fetchall()) == 7

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
    command.downgrade(cfg, "base")

    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        users = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='users'"
            )
        )
        assert users.fetchone() is None
    await engine.dispose()

    command.upgrade(cfg, "head")
