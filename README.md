# Collective Will

## Architecture

For the full system architecture, submission lifecycle, AI pipeline stages, and data
flow diagrams, see **[docs/architecture-flow.md](docs/architecture-flow.md)**.

## Repository Structure

- `docs/` — all project documentation
  - `docs/architecture-flow.md` — **end-to-end architecture & submission flow** (start here)
  - `docs/mvp-specification.md` — product context and frozen decisions
  - `docs/roadmap.md` — v0/v1/v2 roadmap
  - `docs/faq-content.md` — FAQ page content (EN + FA)
  - `docs/CONTRIBUTING.md` — contribution rules and CI parity
  - `docs/agent-context/` — implementation contracts (database, pipeline, messaging, website)
  - `docs/decision-rationale/` — decision rationale, guardrails, LLM strategy, infra guide, decision locks
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
