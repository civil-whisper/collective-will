# Task: Database Connection

## Depends on
- `database/01-project-scaffold` (src/config.py must exist)

## Goal
Set up SQLAlchemy async engine, session factory, and a health check query.

## Files to create/modify

- `src/db/connection.py` — engine, session factory, dependency

## Specification

### Engine and session

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    echo=False,
)

async_session = async_sessionmaker(engine, expire_on_commit=False)
```

### FastAPI dependency

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
```

### Health check

```python
async def check_db_health() -> bool:
    """Returns True if database is reachable."""
    async with async_session() as session:
        result = await session.execute(text("SELECT 1"))
        return result.scalar() == 1
```

### Base model

Define `Base = declarative_base()` (or `DeclarativeBase` subclass) for all ORM models to inherit from.

## Constraints

- Use `asyncpg` as the async driver (the DATABASE_URL should use `postgresql+asyncpg://`).
- Set reasonable pool sizes for MVP scale (not hundreds of connections).
- All database calls must use async/await.

## Tests

Write tests in `tests/test_db/test_connection.py` covering:
- Engine creates successfully with valid DATABASE_URL
- `get_db()` yields a session that can execute a simple query
- `check_db_health()` returns True against a running test database
- `check_db_health()` handles connection failure gracefully (returns False or raises clear error)

Use a test database (not production). Consider pytest fixtures for DB setup/teardown.
