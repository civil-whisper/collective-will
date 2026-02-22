# Collective Will v0 — Shared Context

Every agent receives this file. It is the ground truth for the project.

---

## What This Project Is

Collective Will surfaces what Iranians collectively want. During MVP build/testing, users submit concerns via Telegram, AI agents organize and cluster them, and the community votes on priorities. WhatsApp transport is integrated after MVP once SIM operations are ready. Everything is transparent and auditable.

**v0 goal**: Consensus visibility + approval voting. No action execution (deferred to v1).

**Pilot**: Iran (diaspora + inside-Iran).

---

## v0 Frozen Decisions

These are locked. Do not deviate.

| Decision | Rule |
|----------|------|
| **Scope** | Consensus visibility + approval voting only. No action drafting or execution. |
| **Channel** | Telegram-first for MVP build/testing (official Bot API) while preserving channel-agnostic boundaries (`BaseChannel`). WhatsApp (Evolution API, self-hosted) is deferred until post-MVP rollout once anonymous SIM operations are ready. Keep provider-specific parsing in channel adapters and test with mock/fake channels so transport swaps remain one-module changes. |
| **Canonicalization model** | Claude Sonnet (Farsi → structured English) |
| **LLM routing abstraction** | Model/provider resolution is centralized in `pipeline/llm.py` via config-backed task tiers. No direct model IDs in other modules. |
| **Embeddings** | Quality-first in v0: OpenAI `text-embedding-3-large` (cloud). Later versions may switch to cost-effective embedding models via the LLM abstraction config without business-logic changes. |
| **Cluster summaries** | Quality-first in v0: `english_reasoning` tier defaults to Claude Sonnet. Mandatory fallback is required for risk management (default fallback: DeepSeek `deepseek-chat`) via abstraction config. |
| **User-facing messages** | Quality-first in v0: `farsi_messages` tier defaults to Claude Sonnet. Mandatory fallback is required for risk management (default fallback: Claude Haiku) via abstraction config. |
| **Clustering** | HDBSCAN (runs locally), with config-backed `min_cluster_size` per cycle (v0 default `5`, adjustable by config when needed). Unclustered items (noise) must be visible in analytics and never silently discarded. |
| **Identity** | Email magic-link + WhatsApp account linking. No phone verification, no OAuth, no vouching. Signup controls: exempt major email providers from per-domain cap; enforce `MAX_SIGNUPS_PER_DOMAIN_PER_DAY=3` for non-major domains; enforce per-IP signup cap (`MAX_SIGNUPS_PER_IP_PER_DAY`) and keep telemetry signals (domain diversity, disposable-domain scoring, velocity logs). |
| **Sealed account mapping** | Store messaging linkage as random opaque account refs (UUIDv4). Raw platform IDs (Telegram chat_id, WhatsApp wa_id) live only in the `sealed_account_mappings` DB table and are stripped from logs/exports. The sealed mapping is persisted to database (not in-memory) so it survives restarts. |
| **Auth token persistence** | Magic link tokens and linking codes are stored in the `verification_tokens` DB table with expiry timestamps. No in-memory token storage — tokens must survive process restarts and be shared across background workers. |
| **Submission eligibility** | Verified account + account age >= 48 hours in production. Threshold is config-backed via `MIN_ACCOUNT_AGE_HOURS` (default `48`) so test/dev can override lower values. |
| **Vote eligibility** | Verified account + age >= 48h + at least 1 accepted contribution in production. Accepted contribution = processed submission OR pre-ballot policy endorsement signature. Age threshold config-backed via `MIN_ACCOUNT_AGE_HOURS` (default `48`). Contribution requirement config-backed via `REQUIRE_CONTRIBUTION_FOR_VOTE` (default `true`). Staging/test can override both. |
| **Pre-ballot signatures** | Multi-stage approval is required before ballot: clusters must pass size threshold and collect enough distinct endorsement signatures (`MIN_PREBALLOT_ENDORSEMENTS`, default `5`) before entering final approval ballot. |
| **Voting cycle duration** | Config-backed via `VOTING_CYCLE_HOURS` (default `48`). Staging can use shorter cycles for testing. |
| **Submission daily limit** | Config-backed via `MAX_SUBMISSIONS_PER_DAY` (default `5`). Staging can raise for testing. |
| **Adjudication autonomy** | Individual votes, disputes, and quarantine outcomes are resolved by autonomous agentic workflows (primary model + fallback/ensemble as needed). Humans do not manually decide per-item outcomes; human actions are limited to architecture, policy tuning, and risk-management incidents. |
| **Evidence store** | PostgreSQL append-only hash-chain. No UPDATE/DELETE. |
| **External anchoring** | Merkle root computation is required in v0 (daily). Publishing that root to Witness.co is optional and config-driven. |
| **Infrastructure** | Njalla domain is registered (WHOIS privacy). Primary hosting is 1984.is VPS. Production traffic must pass through a reverse-proxy edge (Cloudflare or OVH DDoS) with origin IP kept private, and an operator failover playbook + standby VPS must be documented. |

### Abuse Thresholds

| Control | Limit |
|---------|-------|
| Submissions per account per day | 5 |
| Accounts per email domain per day | 3 (non-major domains only; major providers exempt) |
| Signups per requester IP per day | 10 |
| Burst quarantine trigger | 3 submissions/5 minutes from one account (soft quarantine: accept + flag for review) |
| Vote changes per cycle | 1 full vote re-submission per cycle (total max: 2 vote submissions/cycle). |
| Failed verification attempts | 5 per email per 24h, then 24h lockout |

### Dispute Handling

- Users flag bad canonicalization or cluster assignment from their dashboard.
- Autonomous dispute-resolution workflow completes within 72 hours (SLA target).
- Resolver can escalate to a stronger model or multi-model ensemble when confidence is low.
- Dispute adjudication must use explicit confidence thresholds with fallback/ensemble paths when below threshold.
- Scope dispute resolution to the disputed submission first (re-canonicalize that item); do not re-run full clustering mid-cycle for a single dispute.
- Disputed items tagged (`dispute_open`, `dispute_resolved`) but never removed or suppressed.
- Resolution logged to evidence store. Resolution is by re-running pipeline, not manual content override.
- Every adjudication action (primary decision, fallback/ensemble escalation, final resolution) must be evidence-logged.
- Track dispute volume and resolver-disagreement metrics; if disputes exceed 5% of cycle submissions (or disagreement spikes), tune model/prompt/policy.

### Data Retention

| Data | Deletable on user request? |
|------|---------------------------|
| Evidence chain entries | No (chain integrity) |
| Account linkage (email ↔ wa_id mapping) | Yes (GDPR) |
| Opaque user refs in evidence chain | No (but unlinkable after account deletion) |
| Raw submissions in evidence chain | No (user link severed; text preserved anonymously) |
| Votes | No (pseudonymous; user link severed on deletion) |

PII safety rule: run automated pre-persist PII detection on incoming submissions. If high-risk PII is detected, do not store the text; ask the user to redact personal identifiers and resend. Keep pipeline PII stripping as a secondary safety layer.

---

## Active Implementation Plan

Execution priorities for the current remediation cycle are tracked in:

- `docs/agent-context/ACTIVE-action-plan.md`

Agents implementing changes should follow that plan order unless the user explicitly re-prioritizes.

---

## Data Models

Implement as Pydantic `BaseModel` subclasses (Python) and SQLAlchemy ORM models for DB.

Model conversion rule: define explicit ORM<->schema conversion methods (for example, `User.from_orm()` / `db_user.to_schema()`), and test round-trip field parity. Avoid ad-hoc dict mapping between ORM and Pydantic layers.

### User

```
id: UUID
email: str
email_verified: bool
messaging_platform: "telegram" | "whatsapp"
messaging_account_ref: str          # Random opaque account ref (UUIDv4), never raw wa_id
messaging_verified: bool
messaging_account_age: datetime | None
created_at: datetime
last_active_at: datetime
locale: "fa" | "en"
trust_score: float                     # Reserved for v1-style risk scoring unless an explicit v0 policy uses it
contribution_count: int              # processed submissions + recorded policy endorsements
is_anonymous: bool
```

### Submission

```
id: UUID
user_id: UUID
raw_text: str
language: str
status: "pending" | "processed" | "flagged" | "rejected"
processed_at: datetime | None
hash: str                           # SHA-256 of raw_text
created_at: datetime
evidence_log_id: int
```

### PolicyCandidate

```
id: UUID
submission_id: UUID
title: str                          # 5-15 words
title_en: str | None
domain: PolicyDomain
summary: str                        # 1-3 sentences
summary_en: str | None
stance: "support" | "oppose" | "neutral" | "unclear"  # "unclear" = model uncertainty; "neutral" = descriptive/no explicit side
entities: list[str]
embedding: list[float]              # pgvector column
confidence: float                   # 0-1
ambiguity_flags: list[str]
model_version: str
prompt_version: str
created_at: datetime
evidence_log_id: int
```

### PolicyDomain (enum)

```
governance, economy, rights, foreign_policy, religion, ethnic, justice, other
```

### Cluster

```
id: UUID
cycle_id: UUID
summary: str                        # Farsi
summary_en: str | None
domain: PolicyDomain
candidate_ids: list[UUID]
member_count: int
centroid_embedding: list[float]
cohesion_score: float
variance_flag: bool
run_id: str
random_seed: int
clustering_params: dict
approval_count: int
created_at: datetime
evidence_log_id: int
```

### Vote

```
id: UUID
user_id: UUID
cycle_id: UUID
approved_cluster_ids: list[UUID]
                                    # v0 storage form; keep vote-approval queries behind db/query helpers for future junction-table migration
created_at: datetime
evidence_log_id: int
```

### PolicyEndorsement

```
id: UUID
user_id: UUID
cluster_id: UUID
created_at: datetime
evidence_log_id: int
```

### VotingCycle

```
id: UUID
started_at: datetime
ends_at: datetime
status: "active" | "closed" | "tallied"
cluster_ids: list[UUID]
results: list[{cluster_id, approval_count, approval_rate}] | None
total_voters: int
evidence_log_id: int
```

### EvidenceLogEntry

```
id: int (BIGSERIAL)
timestamp: datetime
event_type: str                     # submission_received, candidate_created, cluster_created,
                                    # cluster_updated, vote_cast, cycle_opened, cycle_closed,
                                    # user_created, user_verified
entity_type: str
entity_id: UUID
payload: dict                       # JSONB — full entity snapshot
hash: str                           # SHA-256(canonical JSON of {timestamp,event_type,entity_type,entity_id,payload,prev_hash})
prev_hash: str                      # previous entry's hash (chain)
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic |
| **Database** | PostgreSQL 15+ with pgvector extension |
| **Website** | Next.js (App Router), TypeScript, Tailwind CSS, next-intl |
| **Dependency mgmt** | uv (Python), pnpm (Node) |
| **Migrations** | Alembic |
| **Testing** | pytest (Python), vitest or jest (TypeScript) |
| **Linting** | ruff (Python), eslint (TypeScript) |
| **Type checking** | mypy strict (Python) |
| **Containerization** | Docker Compose |

---

## Project Directory Structure

```
collective-will/
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── base.py              # Abstract channel interface
│   │   ├── whatsapp.py          # Evolution API client
│   │   └── types.py             # Unified message format
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── intake.py            # Receives submissions
│   │   ├── voting.py            # Vote prompts, receives votes
│   │   ├── notifications.py     # Sends updates
│   │   ├── identity.py          # Email magic-link, WhatsApp linking
│   │   ├── abuse.py             # Rate limiting, quarantine
│   │   └── commands.py          # Message command router
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── llm.py               # LLM abstraction + router
│   │   ├── privacy.py           # Strip metadata for LLM
│   │   ├── canonicalize.py      # LLM canonicalization
│   │   ├── embeddings.py        # Mistral embed
│   │   ├── cluster.py           # HDBSCAN clustering
│   │   ├── summarize.py         # Cluster summaries
│   │   └── agenda.py            # Agenda building
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── submission.py
│   │   ├── cluster.py
│   │   └── vote.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── evidence.py          # Evidence store operations
│   │   └── queries.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── webhooks.py
│   │   │   ├── analytics.py
│   │   │   ├── user.py
│   │   │   └── auth.py
│   │   └── middleware/
│   │       ├── audit.py
│   │       └── auth.py
│   ├── scheduler.py
│   └── config.py
├── migrations/
│   ├── versions/
│   └── alembic.ini
├── web/                          # Next.js website
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── messages/
│   │   ├── fa.json
│   │   └── en.json
│   ├── package.json
│   └── tsconfig.json
├── tests/                        # Mirrors src/ structure
│   ├── test_channels/
│   ├── test_pipeline/
│   ├── test_handlers/
│   ├── test_api/
│   └── test_db/
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

---

## What's In Scope (v0)

- Telegram submission intake (official Bot API) for MVP build/testing
- Email magic-link verification
- Messaging account linking with opaque account refs (Telegram now; WhatsApp mapping path prepared)
- Canonicalization (Claude Sonnet, cloud)
- Embeddings (quality-first cloud model in v0; cost-optimized model switch later via config)
- Clustering (HDBSCAN, local, batch every 6h)
- Pre-ballot endorsement/signature stage for cluster qualification
- Approval voting via Telegram during MVP build/testing
- Public analytics dashboard (no login wall)
- User dashboard (submissions, votes, disputes)
- Evidence store (hash-chain in Postgres)
- Farsi + English UI (RTL support)
- Audit evidence explorer
- Abuse controls (rate limits, quarantine)

## What's Out of Scope (v0)

- Action execution / drafting
- Signal
- WhatsApp rollout during MVP build/testing (deferred to post-MVP once anonymous SIMs arrive)
- Phone verification, OAuth, vouching
- Quadratic/conviction voting
- Federation / decentralization
- Blockchain anchoring (required)
- Mobile app
- Demographic collection

---

## Process Rules — EVERY AGENT MUST FOLLOW

1. **Test after every task**: When you finish implementing a task, write unit tests for what you just built. Tests go in `tests/` mirroring `src/` structure. Use pytest (Python) or vitest (TypeScript). Run tests and confirm they pass before moving to the next task.
2. **Type hints everywhere**: All Python functions have type annotations. Run mypy in strict mode.
3. **Pydantic for all models**: All data models are Pydantic BaseModel subclasses. SQLAlchemy models are separate but aligned.
4. **Parameterized queries only**: Use SQLAlchemy ORM. No string concatenation for SQL.
5. **Use `secrets` not `random`**: For any crypto/token generation.
6. **No eval/exec**: Never execute dynamic code.
7. **Ruff for formatting**: Run ruff before finishing.
8. **Never commit secrets**: `.env` is gitignored. No API keys, passwords, or tokens in code.
9. **OpSec**: No real names in commits/comments/code. No hardcoded paths containing usernames. Store only opaque account refs in core tables/logs; raw `wa_id` is allowed only in the sealed mapping.
10. **No per-item human adjudication**: Humans do not manually approve/reject single votes, disputes, or quarantined submissions. They may only change policy/config, architecture, and risk-management controls.
