# Task: Docker Compose

## Depends on
- `database/05-alembic-migrations` (migrations exist to initialize DB)
- `database/01-project-scaffold` (pyproject.toml, project structure)

## Goal
Create Docker Compose configuration for local development and a Dockerfile for the Python backend. Running `docker compose up` should start Postgres, Evolution API, and the backend.

## Files to create/modify

- `docker-compose.yml` — development services
- `Dockerfile` — Python backend image
- `src/api/main.py` — FastAPI app with health check endpoint (if not already created)

## Specification

### docker-compose.yml

Services:

**postgres**
- Image: `pgvector/pgvector:pg15`
- Env: `POSTGRES_USER=collective`, `POSTGRES_PASSWORD=${DB_PASSWORD}`, `POSTGRES_DB=collective_will`
- Port: `5432:5432`
- Volume: `./data/postgres:/var/lib/postgresql/data`
- Healthcheck: `pg_isready -U collective`

**evolution**
- Image: `atendai/evolution-api:latest`
- Env: `AUTHENTICATION_API_KEY=${EVOLUTION_API_KEY}`, `DATABASE_ENABLED=false`
- Port: `8080:8080`
- Volume: `./data/evolution:/evolution/instances`

**backend**
- Build from `Dockerfile`
- Command: `uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload`
- Env: all vars from `.env` (use `env_file: .env`)
- Port: `8000:8000`
- Depends on: postgres (healthy), evolution
- Volume: `.:/app` (for hot reload during development)

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy source
COPY . .

CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### FastAPI health check

If `src/api/main.py` doesn't exist yet, create it:

```python
from fastapi import FastAPI

app = FastAPI(title="Collective Will", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok"}
```

Add a `/health/db` endpoint that calls `check_db_health()` from `src/db/connection.py`.

### .env updates

Add to `.env.example`:
```
DB_PASSWORD=local_dev_password
APP_PUBLIC_BASE_URL=https://collectivewill.org
```

Ensure `DATABASE_URL` in `.env.example` uses `postgresql+asyncpg://collective:${DB_PASSWORD}@localhost:5432/collective_will` format.

## Constraints

- Do NOT expose Postgres to the internet (no `0.0.0.0` binding in production). For local dev, `5432:5432` is fine.
- The backend container must wait for Postgres to be healthy before starting.
- Do NOT include any secrets in the Dockerfile or docker-compose.yml. All secrets come from `.env`.
- Do NOT run containers as root. Add a non-root `USER` in the Dockerfile.
- This compose file is for local dev only. In production, put backend behind a reverse-proxy edge (Cloudflare or OVH), keep origin IP private, and do not expose backend directly on public internet.
- Maintain an operator failover playbook for standby VPS + DNS cutover.

## Tests

Write tests in `tests/test_api/test_health.py` covering:
- `GET /health` returns 200 with `{"status": "ok"}`
- `GET /health/db` returns 200 when database is reachable
- `GET /health/db` returns 503 when database is unreachable

Also verify manually:
- `docker compose up -d` starts all three services
- `docker compose ps` shows all services healthy
- `curl http://localhost:8000/health` returns 200
