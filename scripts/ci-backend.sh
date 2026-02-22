#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DEFAULT_DB_URL="postgresql+asyncpg://collective:testpass@localhost:5432/collective_will_test"
DB_CONTAINER_NAME="${DB_CONTAINER_NAME:-collective-will-ci-postgres}"
KEEP_LOCAL_CI_DB="${KEEP_LOCAL_CI_DB:-0}"
STARTED_LOCAL_DB=0

export DATABASE_URL="${DATABASE_URL:-$DEFAULT_DB_URL}"
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-$DATABASE_URL}"
export ENVIRONMENT="${ENVIRONMENT:-test}"
export GENERATE_PIPELINE_CACHE="${GENERATE_PIPELINE_CACHE:-0}"
export CI_PARITY=1

cleanup() {
  if [[ "$STARTED_LOCAL_DB" -eq 1 && "$KEEP_LOCAL_CI_DB" != "1" ]]; then
    docker rm -f "$DB_CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

can_connect() {
  uv run python - <<'PY' >/dev/null 2>&1
import asyncio
import os
import asyncpg

async def main() -> int:
    try:
        conn = await asyncpg.connect(os.environ["TEST_DATABASE_URL"], timeout=2)
        await conn.close()
        return 0
    except Exception:
        return 1

raise SystemExit(asyncio.run(main()))
PY
}

start_local_pgvector_if_needed() {
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    return
  fi

  if can_connect; then
    return
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "Postgres not reachable and docker is unavailable. Set TEST_DATABASE_URL to a reachable test DB."
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "Postgres not reachable and docker daemon is not running."
    echo "Start docker or export TEST_DATABASE_URL to a reachable Postgres instance."
    exit 1
  fi

  if docker inspect "$DB_CONTAINER_NAME" >/dev/null 2>&1; then
    docker start "$DB_CONTAINER_NAME" >/dev/null 2>&1 || true
  else
    docker run -d \
      --name "$DB_CONTAINER_NAME" \
      -e POSTGRES_USER=collective \
      -e POSTGRES_PASSWORD=testpass \
      -e POSTGRES_DB=collective_will_test \
      -p 5432:5432 \
      pgvector/pgvector:pg15 >/dev/null
    STARTED_LOCAL_DB=1
  fi

  for _ in $(seq 1 30); do
    if can_connect; then
      return
    fi
    sleep 2
  done

  echo "Timed out waiting for Postgres at TEST_DATABASE_URL=${TEST_DATABASE_URL}"
  exit 1
}

echo "==> Sync dependencies"
uv sync

echo "==> Ensure Postgres parity target"
start_local_pgvector_if_needed

if ! can_connect; then
  echo "Cannot connect to TEST_DATABASE_URL=${TEST_DATABASE_URL}"
  exit 1
fi

echo "==> Ruff"
uv run ruff check src/ tests/

echo "==> Backend tests (CI parity set)"
uv run pytest --tb=short -q \
  --ignore=tests/test_pipeline/test_pipeline_comprehensive.py \
  --ignore=tests/test_integration/test_telegram_e2e.py

echo "==> Cached replay integration test"
uv run pytest --tb=short -q tests/test_pipeline/test_pipeline_cached_replay.py

echo "Backend CI parity checks passed."
