# Task: Alembic Migrations

## Depends on
- `database/03-core-models` (all ORM models defined)
- `database/04-evidence-store` (evidence_log model and DDL)

## Goal
Set up Alembic for async SQLAlchemy and create the initial migration that builds all tables, the evidence_log trigger, and indexes.

## Files to create/modify

- `alembic.ini` — Alembic configuration
- `migrations/env.py` — async migration environment
- `migrations/script.py.mako` — migration template
- `migrations/versions/001_initial_schema.py` — initial migration

## Specification

### alembic.ini

- Set `sqlalchemy.url` to read from environment (or use `env.py` to override from `Settings`).
- Set `script_location = migrations`

### migrations/env.py

Configure for async SQLAlchemy:
- Import all ORM models so Alembic detects them
- Use `run_async_migrations()` pattern with `connectable = create_async_engine(...)`
- Import `Base.metadata` as the target metadata

### Initial migration (001_initial_schema.py)

The `upgrade()` function must create:

1. **pgvector extension**: `CREATE EXTENSION IF NOT EXISTS vector`
2. **users** table
3. **submissions** table (FK to users)
4. **policy_candidates** table (FK to submissions, pgvector column)
5. **voting_cycles** table
6. **clusters** table (FK to voting_cycles, pgvector column)
7. **votes** table (FK to users, FK to voting_cycles)
8. **evidence_log** table with indexes
9. **Evidence chain trigger**: SQL trigger function that validates prev_hash on INSERT
10. **Revoke UPDATE/DELETE** on evidence_log: `REVOKE UPDATE, DELETE ON evidence_log FROM collective` (the app DB user)

The `downgrade()` function must drop all tables and the extension in reverse order.

## Constraints

- The migration must be idempotent-safe — running `alembic upgrade head` on a fresh database works cleanly.
- Use `op.execute()` for raw SQL (trigger creation, permission revocation, extension creation).
- Do NOT auto-generate the migration. Write it explicitly to ensure the evidence_log trigger and permissions are included.

## Tests

Write tests in `tests/test_db/test_migrations.py` covering:
- `alembic upgrade head` completes without error on an empty test database
- All expected tables exist after migration (query `information_schema.tables`)
- `alembic downgrade base` removes all tables
- `alembic upgrade head` can be run again after downgrade (round-trip)
- The evidence_log trigger exists (query `pg_trigger`)
- pgvector extension is installed (query `pg_extension`)
