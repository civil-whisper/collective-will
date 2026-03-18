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
| `src/api/rate_limit.py` | In-process sliding-window rate limiters + `get_request_ip()` (CF-Connecting-IP preferred) |
| `src/channels/base.py` | `BaseChannel` ABC — platform-agnostic interface (includes `download_file` for voice) |
| `src/voice/client.py` | `VoiceCloudClient` — orchestrates OpenAI transcription + Modal embedding |
| `src/voice/transcription.py` | OpenAI GPT-4o-transcribe API client |
| `src/voice/embedding.py` | Modal serverless embedding API client |
| `src/voice/transcription_scoring.py` | Word-overlap (EN) and subsequence+homophone (FA) scoring |
| `src/voice/scoring.py` | Cosine similarity, decision matrix, embedding serialize/deserialize |
| `src/voice/enrollment.py` | Multi-step enrollment state machine (3 phrases → averaged embedding + audio storage) |
| `src/voice/verification.py` | Session verification: dual check (embedding + transcription) |
| `src/voice/phrases.py` | Phrase pool loaded from `voice-phrases.json` (gitignored secret), random selection |
| `src/models/enrollment_audio.py` | Raw enrollment audio storage for model portability |
| `modal_functions/voice_embedding.py` | Modal serverless function: ECAPA2 speaker embedding |
| `src/ops/monitor.py` | Ops monitor: health checks, alert/heartbeat emails, dedup state |
| `src/email/sender.py` | Email transport: magic links + operator alerts via Resend |
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

All LLM calls go through `LLMRouter` in `src/pipeline/llm.py`. Task tiers are config-backed via env vars — no model IDs outside `llm.py`. Default primary: `claude-sonnet-4-6`. Default fallback: `gpt-4o`. Embeddings: `gemini-embedding-001` (primary), `text-embedding-3-large` (fallback). Web search grounding is supported for Anthropic (`web_search_20250305`), Google (`google_search`), and OpenAI (Responses API `web_search_preview`). Provider-side prompt caching is enabled by default (`LLM_PROMPT_CACHING_ENABLED=true`): Anthropic system prompts are sent as block arrays with `cache_control`, OpenAI automatic cache hits are captured. Cache telemetry (`cache_read_tokens`, `cache_write_tokens`) is tracked in `LLMResponse`.

### Evidence Hash-Chain

Every significant action produces an `EvidenceLogEntry` with `SHA-256({timestamp, event_type, entity_type, entity_id, payload, prev_hash})`. The chain is append-only — no UPDATE/DELETE. The public `GET /analytics/evidence` endpoint applies recursive PII stripping + per-event visibility-tier filtering (delayed fields hidden during active voting cycles). Valid event types and their visibility specs are defined in `EVENT_CATALOG` in `src/db/evidence.py`. Receipt-eligible events (`policy_endorsed`, `vote_cast`) generate HMAC receipt tokens for user-verifiable proof of inclusion via `GET /user/dashboard/receipts`.

### Channel Abstraction

Business logic uses `UnifiedMessage` / `OutboundMessage` — never platform-specific types. `TelegramChannel` is active for MVP. `WhatsAppChannel` (Evolution API) is implemented but deferred post-MVP. Adding a new transport is a one-module change.

---

## Hard Constraints (from AGENTS.md and docs/decision-rationale/DECISION_LOCKS.md)

- **No per-item human adjudication** for votes, disputes, or quarantine outcomes — autonomous only.
- **All LLM calls through `LLMRouter`** — no direct model IDs in business logic or handlers.
- **Raw platform IDs** (`telegram chat_id`, `wa_id`) live only in `sealed_account_mappings` — never in core tables, logs, or exports.
- **Evidence store is append-only** — no UPDATE/DELETE on `evidence_log`.
- **Auth tokens must be DB-persisted** — no in-memory token storage (must survive restarts).
- **No raw `x-user-email` headers for auth** — only backend-verified bearer tokens.
- **Keep `BaseChannel` boundary** — no platform-specific logic in handlers or pipeline.
- **Generic auth error messages** — auth failure responses must not distinguish between invalid/expired/not-found to prevent enumeration.
- **Token consumption must be atomic** — use `SELECT ... FOR UPDATE` + flush in `consume_token()`.
- **CORS explicit whitelists** — never use `allow_methods=["*"]` or `allow_headers=["*"]`.
- **Telegram webhook must verify signature** — when `TELEGRAM_WEBHOOK_SECRET` is configured, reject requests without valid `X-Telegram-Bot-Api-Secret-Token`.
- **IP resolution via `get_request_ip()`** — all rate-limiting code must use `src/api/rate_limit.py:get_request_ip()` (prefers `CF-Connecting-IP`), not raw `X-Forwarded-For`.

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

## Workflow Rules (from .cursor/rules)

### CI Before Commit
Before committing and pushing, run `scripts/ci-backend.sh` for backend changes and `scripts/ci-web.sh` for web changes. Run both unless the change is clearly scoped to only one side. Fix any failures before committing.

### Post-Implementation Context Update
After completing any task that changes behavior, models, APIs, or flow:
1. Update affected `docs/agent-context/**` files (implementation contracts: models, signatures, flow, constraints, test inventories).
2. Update `docs/decision-rationale/**` if the *why* or guardrails changed.
3. Update `docs/agent-context/CONTEXT-shared.md` if data models, event types, directory structure, or frozen decisions changed.
4. Update `docs/agent-context/ACTIVE-action-plan.md` — mark completed items, add discovered work.
Context drift between code and docs causes future agents to make incorrect assumptions. Treat context updates as part of the task, not a follow-up.

### Context Governance Loop
When a discussion creates a stable, reusable project decision (not a one-off task):
- Promote it to durable sources following documentation precedence order.
- Keep `docs/agent-context/**` as implementation contracts and `docs/decision-rationale/**` as rationale/guardrails.
- Keep `AGENTS.md` aligned when shared constraints or hard requirements change.
- Avoid churn: only persist confirmed direction, not temporary or speculative decisions.

### Context Documentation Sync
- Keep `docs/agent-context/**` focused on implementation contracts.
- Keep `docs/decision-rationale/**` focused on why and guardrails.
- Avoid introducing contradictions across `AGENTS.md`, context docs, and decision docs.

### Python Delivery Discipline
- Add or update tests for each implemented task.
- Keep business logic model-agnostic; route LLM selection through configuration.
- Never include secrets, personal identities, or raw sensitive identifiers in code or fixtures.

### Infra and Migration Guardrails
When changing infrastructure or schema migration files:
- Preserve append-only evidence logging and hash-chain compatibility.
- Keep sensitive identifier boundaries intact (no raw external IDs in core tables).
- Keep schema changes backward-safe for rolling deployments when possible.
- Document rationale in `docs/decision-rationale/**` when a migration changes architecture assumptions.
- Keep environment-specific values in config/secrets, not hardcoded in migration or compose files.

### Emergent Rule Capture
While working, watch for repeating patterns (same fix in multiple places, manual steps repeated, corrective loops, recurring structural choices). When a pattern repeats at least twice and is not already covered by an existing rule: surface it to the user and, on confirmation, capture it as a new rule in `.cursor/rules/` (or add to this file).
