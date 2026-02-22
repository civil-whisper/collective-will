# Collective Will

## Repository Structure

- `docs/` — all project documentation
  - `docs/agent-context/` — implementation contracts (30 tasks across database, pipeline, messaging, website)
  - `docs/decision-rationale/` — decision rationale and guardrails
  - `docs/mvp-specification.md`
  - `docs/llm-strategy.md`
  - `docs/infrastructure-guide.md`
  - `docs/roadmap.md`
  - `docs/v0-precoding-checklist.md`
  - `docs/CONTRIBUTING.md`
  - `docs/DECISION_LOCKS.md`
- `src/` — Python backend (FastAPI, SQLAlchemy, pipeline)
- `web/` — Next.js frontend (i18n, analytics, dashboard)
- `migrations/` — Alembic database migrations
- `tests/` — Backend test suite
- `AGENTS.md` — Agent bootstrap rules
- `.env.example` — Environment variable template

## Getting Started

1. Copy `.env.example` to `.env` and fill in values.
2. Run `docker-compose up` for local development (Postgres + backend).
3. In `web/`, run `npm install && npm run dev` for the frontend.
4. Run `pytest` for backend tests, `npm test` in `web/` for frontend tests.
