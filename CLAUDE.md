# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Commands

### Backend (Python / uv)

```bash
# Install dependencies
uv sync

# Run backend tests (requires Postgres — script auto-starts a pgvector container if Docker is available)
bash scripts/ci-backend.sh

# Run a single test file
uv run pytest tests/test_pipeline/test_canonicalize.py --tb=short -q

# Run a single test by name
uv run pytest -k "test_name" --tb=short

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/

# Run backend server
uv run uvicorn src.api.main:app --reload

# Run batch scheduler
uv run python -m src.scheduler
```

### Frontend (Next.js / npm)

```bash
cd web

# Install deps
npm ci

# Dev server
npm run dev

# Lint
npm run lint

# Type check
npm run typecheck

# Tests
npm test

# Production build
npm run build
```

### Full CI parity (what GitHub CI runs)

```bash
bash scripts/ci-backend.sh   # Backend: ruff + pytest + DB required
bash scripts/ci-web.sh       # Frontend: lint + typecheck + vitest + next build
```

### Database migrations

```bash
# Apply migrations
uv run alembic upgrade head

# Create a new migration
uv run alembic revision --autogenerate -m "description"
```

---

## Architecture

The full system flow is documented in `docs/architecture-flow.md`. The short version:

**Submission → inline AI pipeline → batch pipeline → voting cycle → public results**

1. User sends text via **Telegram bot** → `src/handlers/commands.py` routes to the appropriate handler
2. `src/handlers/intake.py` runs eligibility/PII checks, creates a `Submission`, then immediately calls the inline AI pipeline:
   - `src/pipeline/canonicalize.py` → LLM converts free Farsi text to a structured English `PolicyCandidate` with `policy_topic` + `policy_key`
   - `src/pipeline/embeddings.py` → vector embedding stored in pgvector
3. **Batch scheduler** (`src/scheduler/`) runs periodically:
   - Groups candidates by `policy_key` into `Cluster` records
   - Runs hybrid normalization to merge near-duplicate keys (cosine similarity + LLM re-mapping)
   - Generates ballot questions and 2–4 stance `PolicyOption`s per cluster
   - Builds the agenda (endorsement threshold check)
4. Users endorse clusters via Telegram → once a cluster passes the threshold, it enters a `VotingCycle`
5. Users vote per-policy via Telegram inline keyboards → cycle tallies → results on public analytics site

### Key Source Paths

| Path | Purpose |
|------|---------|
| `src/pipeline/llm.py` | `LLMRouter` — all LLM calls must go through this; config-backed task tiers, fallback, retry |
| `src/pipeline/canonicalize.py` | Submission → structured `PolicyCandidate` |
| `src/pipeline/cluster.py` | Policy-key grouping into `Cluster` records |
| `src/pipeline/normalize.py` | Hybrid normalization (embedding similarity + LLM merge) |
| `src/pipeline/options.py` | LLM-generated per-policy stance options |
| `src/pipeline/agenda.py` | Endorsement threshold → ballot qualification |
| `src/pipeline/endorsement.py` | Ballot question generation |
| `src/db/evidence.py` | Append-only hash-chain evidence store |
| `src/handlers/commands.py` | Telegram message router |
| `src/api/main.py` | FastAPI app entry point |
| `src/api/routes/` | REST endpoints: analytics, user, auth, webhooks |
| `src/channels/base.py` | `BaseChannel` ABC — platform-agnostic interface |
| `src/scheduler/main.py` | `run_pipeline()` — full batch pipeline orchestration |
| `web/lib/api.ts` | Auto-selects `BACKEND_API_BASE_URL` (server) vs `NEXT_PUBLIC_API_BASE_URL` (browser) |
| `web/app/` | Next.js App Router pages |
| `web/messages/fa.json` | Farsi i18n strings |
| `web/messages/en.json` | English i18n strings |
| `migrations/` | Alembic migration versions |

### Web Auth Flow

Magic-link email → verify → exchange `web_session_code` for a signed bearer token (HMAC-SHA256 via `WEB_ACCESS_TOKEN_SECRET`). Token stored in NextAuth JWT cookie; API routes read `Authorization: Bearer ...`. All auth tokens (magic link, linking code, web session) live in the `verification_tokens` DB table — no in-memory state.

Caddy reverse proxy splits `/api/auth/*` between the backend and NextAuth: use `handle` + `uri strip_prefix /api` for backend routes; **never `handle_path`**.

### LLM Routing

All LLM calls go through `LLMRouter` in `src/pipeline/llm.py`. Task tiers are config-backed via env vars — no model IDs outside `llm.py`. Default primary: `claude-sonnet-4-6`. Default fallback: `gemini-3.1-pro-preview`. Embeddings: `gemini-embedding-001` (primary), `text-embedding-3-large` (fallback).

### Evidence Hash-Chain

Every significant action produces an `EvidenceLogEntry` with `SHA-256({timestamp, event_type, entity_type, entity_id, payload, prev_hash})`. The chain is append-only — no UPDATE/DELETE. The public `GET /analytics/evidence` endpoint strips PII keys (`user_id`, `email`, `account_ref`, `wa_id`) from payloads. Valid event types are enforced in `src/db/evidence.py` via `VALID_EVENT_TYPES`.

### Channel Abstraction

Business logic uses `UnifiedMessage` / `OutboundMessage` — never platform-specific types. `TelegramChannel` is active for MVP. `WhatsAppChannel` (Evolution API) is implemented but deferred post-MVP. Adding a new transport is a one-module change.

---

## Hard Constraints (from AGENTS.md and docs/DECISION_LOCKS.md)

- **No per-item human adjudication** for votes, disputes, or quarantine outcomes — autonomous only.
- **All LLM calls through `LLMRouter`** — no direct model IDs in business logic or handlers.
- **Raw platform IDs** (`telegram chat_id`, `wa_id`) live only in `sealed_account_mappings` — never in core tables, logs, or exports.
- **Evidence store is append-only** — no UPDATE/DELETE on `evidence_log`.
- **Auth tokens must be DB-persisted** — no in-memory token storage (must survive restarts).
- **No raw `x-user-email` headers for auth** — only backend-verified bearer tokens.
- **Keep `BaseChannel` boundary** — no platform-specific logic in handlers or pipeline.

## Code Style

- Python: strict mypy, ruff (line-length 120), `secrets` for crypto/tokens, `asyncio`, SQLAlchemy ORM only (no raw SQL string concatenation), explicit ORM↔Pydantic conversion methods.
- TypeScript: `tsc --noEmit` must pass, vitest for tests, Next.js App Router conventions.
- Tests mirror `src/` in `tests/` (Python) and `web/tests/` (frontend).

## Documentation Precedence

When implementing anything, read in this order:
1. `docs/agent-context/CONTEXT-shared.md` — global ground truth
2. `docs/agent-context/**` — module-level contracts
3. `docs/decision-rationale/**` — why + guardrails
4. `docs/mvp-specification.md` — product context

Active implementation priorities: `docs/agent-context/ACTIVE-action-plan.md`.
