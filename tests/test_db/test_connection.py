from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db import connection


def test_engine_created(monkeypatch: pytest.MonkeyPatch) -> None:
    connection.get_engine.cache_clear()
    connection.get_sessionmaker.cache_clear()
    engine = connection.get_engine()
    assert str(engine.url).startswith("postgresql+asyncpg://")
    assert engine.pool.size() == 5  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_db_yields_session(test_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(test_database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(connection, "get_sessionmaker", lambda: maker)

    generator = connection.get_db()
    session = await anext(generator)
    result = await session.execute(text("SELECT 1"))
    assert result.scalar() == 1
    await generator.aclose()
    await engine.dispose()


@pytest.mark.asyncio
async def test_check_db_health_true(test_database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(test_database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(connection, "get_sessionmaker", lambda: maker)

    assert await connection.check_db_health() is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_check_db_health_false(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenContextManager:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

        async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

    class BrokenMaker:
        def __call__(self):  # type: ignore[no-untyped-def]
            return BrokenContextManager()

    monkeypatch.setattr(connection, "get_sessionmaker", lambda: BrokenMaker())
    assert await connection.check_db_health() is False
