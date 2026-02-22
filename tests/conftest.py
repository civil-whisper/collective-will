from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src import models  # noqa: F401
from src.db.connection import Base


@pytest.fixture(autouse=True)
def _default_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://collective:pw@localhost:5432/collective_will"
    )
    monkeypatch.setenv("APP_PUBLIC_BASE_URL", "https://collectivewill.org")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    monkeypatch.setenv("EVOLUTION_API_KEY", "x")
    from src.config import get_settings

    get_settings.cache_clear()


def requires_test_db() -> bool:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    return bool(test_database_url and test_database_url.startswith("postgresql+asyncpg://"))


@pytest.fixture(scope="session")
def test_database_url() -> str:
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not requires_test_db():
        if os.getenv("CI_PARITY") == "1":
            pytest.fail("CI parity mode requires TEST_DATABASE_URL to be set to a Postgres asyncpg URL")
        pytest.skip("TEST_DATABASE_URL not set for postgres integration tests")
    assert test_database_url is not None
    return test_database_url


@pytest.fixture
async def db_session(test_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(test_database_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
