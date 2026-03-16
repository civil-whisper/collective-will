# Collective Will v0 — Shared Context

Every agent receives this file. It is the ground truth for the project.

---

## What This Project Is

Collective Will surfaces what Iranians collectively want. During MVP build/testing, users submit concerns via Telegram, AI agents organize and cluster them, and the community votes on priorities. WhatsApp transport is integrated after MVP once SIM operations are ready. Everything is transparent and auditable.

**v0 goal**: Consensus visibility + per-policy stance voting with LLM-generated options. No action execution (deferred to v1).

**Pilot**: Iran (diaspora + inside-Iran).

---

## v0 Frozen Decisions

These are locked. Do not deviate.

| Decision | Rule |
|----------|------|
| **Scope** | Consensus visibility + per-policy stance voting only. No action drafting or execution. |
| **Channel** | Telegram-first for MVP build/testing (official Bot API) while preserving channel-agnostic boundaries (`BaseChannel`). WhatsApp (Evolution API, self-hosted) is deferred until post-MVP rollout once anonymous SIM operations are ready. Keep provider-specific parsing in channel adapters and test with mock/fake channels so transport swaps remain one-module changes. |
| **Canonicalization model** | Claude Sonnet 4.6 (any language → structured English). Runs inline at submission time with batch fallback. Accepts positions, questions, concerns, and expressions of interest about policy topics — not just explicit stances. Fallback: `gpt-4o`. Canonicalization prompts are split into a stable instruction prefix (`_CANONICALIZATION_INSTRUCTIONS`) plus dynamic context and input, so provider-side prefix caching maximizes reuse. Open-key context is capped by `CANONICALIZATION_CONTEXT_MAX_ENTRIES` and `CANONICALIZATION_CONTEXT_SUMMARY_CHARS`. |
| **LLM routing abstraction** | Model/provider resolution is centralized in `pipeline/llm.py` via config-backed task tiers. No direct model IDs in other modules. |
| **LLM model strategy** | Claude-first: all primary tiers default to `claude-sonnet-4-6`. All fallbacks default to `gpt-4o` (switched from `gemini-3.1-pro-preview` due to Gemini rate limits). Model selection is config-backed — switch any tier via env without code changes. Web search grounding supported for Anthropic, Google, and OpenAI. Provider-side prompt caching enabled by default (`LLM_PROMPT_CACHING_ENABLED=true`): Anthropic system blocks get `cache_control`, OpenAI automatic cache hits are captured. Cache telemetry exposed in `LLMResponse` and replay stats. |
| **Embeddings** | Gemini-first in v0: `gemini-embedding-001` (primary), `text-embedding-3-large` (fallback). Model selection/fallback controlled by config. |
| **Cluster summaries** | `english_reasoning` tier defaults to Claude Sonnet 4.6. Mandatory fallback (`gpt-4o`) is required for risk management via abstraction config. |
| **Policy option generation** | `option_generation` defaults to Claude Sonnet 4.6 with explicit `gpt-4o` fallback. Grounding is **conditional and off by default**; enable it only for configured research-heavy topics (for example `digital-rights`) via `OPTION_GENERATION_GROUNDING_*` settings. Parser salvage runs before model fallback so wrapper prose/fenced JSON does not trigger generic fallback unnecessarily. |
| **User-facing messages** | Locale-aware (Farsi + English, keyed by `user.locale`). LLM-generated content (rejection reasons) matches the input language. Template-based messages (confirmation, errors) use the `_MESSAGES` dict with locale selection. LLM tier `farsi_messages` defaults to Claude Sonnet 4.6 with mandatory fallback (`gpt-4o`) via abstraction config. |
| **Clustering** | LLM-driven policy-key grouping. Each submission is assigned a stance-neutral `policy_key` as the ballot-level identity. `policy_topic` is retained only as browsing/display metadata, sanitized to simple lowercase-with-hyphens, and must not drive grouping or merge decisions. Canonicalization also emits semantic fields (`actor_scope`, `action_mechanism`, `target_scope`) plus `ballot_readiness` (`ballot-ready`, `needs-refinement`, `discussion-only`). `discussion-only` is reserved for open exploration with no implied proposition; `needs-refinement` means a real proposition exists but needs narrower scope. Compound submissions should be flagged with `compound_submission` rather than silently merged into vague keys. Clusters are persistent entities keyed by `policy_key`; only ballot-ready clusters may advance to policy option generation and voting. Hybrid normalization must preserve actor/mechanism/target compatibility and abstain when items would not share the same proposition and option set. |
| **Identity** | Email magic-link + WhatsApp account linking. No phone verification, no OAuth, no vouching. Signup controls: exempt major email providers from per-domain cap; enforce `MAX_SIGNUPS_PER_DOMAIN_PER_DAY=3` for non-major domains; enforce per-IP signup cap (`MAX_SIGNUPS_PER_IP_PER_DAY`) and keep telemetry signals (domain diversity, disposable-domain scoring, velocity logs). |
| **Sealed account mapping** | Store messaging linkage as random opaque account refs (UUIDv4). Raw platform IDs (Telegram chat_id, WhatsApp wa_id) live only in the `sealed_account_mappings` DB table and are stripped from logs/exports. The sealed mapping is persisted to database (not in-memory) so it survives restarts. |
| **Auth token persistence** | Magic link tokens and linking codes are stored in the `verification_tokens` DB table with expiry timestamps. No in-memory token storage — tokens must survive process restarts and be shared across background workers. |
| **Authenticated web API identity** | `/user/*` and `/ops/*` must use backend-verified bearer tokens derived from the magic-link web session flow. Do not trust client-provided identity headers (for example `x-user-email`) for authenticated access control. Keep bearer signing secret backend-only via `WEB_ACCESS_TOKEN_SECRET`. |
| **Submission eligibility** | Verified account + account age >= 48 hours in production. Threshold is config-backed via `MIN_ACCOUNT_AGE_HOURS` (default `48`) so test/dev can override lower values. |
| **Vote eligibility** | Verified account + age >= 48h + at least 1 accepted contribution in production. Accepted contribution = processed submission OR pre-ballot policy endorsement signature. Age threshold config-backed via `MIN_ACCOUNT_AGE_HOURS` (default `48`). Contribution requirement config-backed via `REQUIRE_CONTRIBUTION_FOR_VOTE` (default `true`). Staging/test can override both. |
| **Pre-ballot signatures** | Multi-stage approval is required before ballot: concerns first gather signatures/endorsements as agenda-setting items. Only clusters classified as `ballot-ready` may advance from endorsement into final voting. Broad concerns can remain visible as `discussion-only` or `needs-refinement` items while the system autonomously refines them into clearer proposition drafts. Refinement generation should run only for clusters with at least one `needs-refinement` member; pure `discussion-only` clusters stay as civic discussion topics with no option set. Those refinement drafts are stored at the cluster level with confidence + clarification flags and are visible on the website, but they do not automatically promote a cluster into voting. |
| **Voting cycle duration** | Config-backed via `VOTING_CYCLE_HOURS` (default `48`). Staging can use shorter cycles for testing. |
| **Submission daily limit** | Config-backed via `MAX_SUBMISSIONS_PER_DAY` (default `5`). Staging can raise for testing. |
| **Adjudication autonomy** | Individual votes, disputes, and quarantine outcomes are resolved by autonomous agentic workflows (primary model + fallback/ensemble as needed). Humans do not manually decide per-item outcomes; human actions are limited to architecture, policy tuning, and risk-management incidents. |
| **Evidence store** | PostgreSQL append-only hash-chain. No UPDATE/DELETE. |
| **External anchoring** | Merkle root computation is required in v0 (daily). External timestamping is optional and config-driven via `AUDIT_TIMESTAMP_PROVIDER` (`none` or `opentimestamps`). Current public-verifiability pattern: publish one **daily redacted audit bundle** + manifest + detached OpenTimestamps proof for the UTF-8 bytes of that day's `daily_merkle_root`. |
| **Ops observability console** | Add a separate `/ops` diagnostics surface for runtime health/events. In dev/staging it may appear in top navigation; in production it must be admin-auth gated and feature-flagged. Show structured, redacted operational events (health checks, recent errors, job status, webhook/email transport status), not raw container logs. |
| **Infrastructure** | Njalla domain is registered (WHOIS privacy). Primary hosting is 1984.is VPS. Cloudflare (Free plan) is **active** as the edge proxy — DNS, CDN, DDoS protection, and Bot Fight Mode enabled. Caddy `trusted_proxies static` is configured with all Cloudflare IP ranges + `trusted_proxies_strict` to preserve real client IPs. Production domain serves a static 503 maintenance page until the production stack is deployed (staging is the active environment). Deploy pipeline includes preflight checks, pull retries with backoff, and post-deploy health gates. Origin IP is private. Operator failover playbook + standby VPS must be documented. |
| **Web dependency security** | Next.js ≥15.5.12, React ≥19.0.1 (patched for CVE-2025-66478). No wget/curl in web runtime image. Deploy SSH timeout 10m — do not lengthen to mask anomalies. Full incident context: `docs/agent-context/security/01-nextjs-rce-cryptomining-2025-03.md`. |
| **Telegram webhook verification** | When `TELEGRAM_WEBHOOK_SECRET` is set, the Telegram webhook endpoint verifies the `X-Telegram-Bot-Api-Secret-Token` header using `hmac.compare_digest`. The same secret must be passed to Telegram's `setWebhook` API. |
| **Auth endpoint rate limiting** | In-process sliding-window rate limiters protect auth endpoints: `/auth/subscribe` (5/min/IP), `/auth/verify` (10/min/IP), `/auth/web-session` (5/min/IP). Disputes are limited to 3/hour/user. Voice verification is limited to 5/hour/user. Implementation: `src/api/rate_limit.py`. For horizontal scaling, replace with Redis-backed counters. |
| **Generic auth error messages** | Auth failure responses use generic messages ("Invalid or expired verification link", "Invalid or expired session code") to prevent account enumeration. Internal error codes (e.g., `invalid_token`, `expired_token`, `user_not_found`) are not exposed to clients. |
| **IP resolution** | `get_request_ip()` in `src/api/rate_limit.py` prefers `CF-Connecting-IP` (non-spoofable behind Cloudflare) over `X-Forwarded-For`. All auth routes use this function for IP-based rate limiting. |
| **CORS policy** | Backend CORS allows only explicit origins (from `CORS_ALLOW_ORIGINS`), methods `GET/POST/OPTIONS`, and headers `Content-Type/Authorization`. No wildcard methods or headers. |
| **Security headers** | Caddy sets `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` on all staging responses. `Server` header is stripped. |
| **Token consumption atomicity** | `consume_token()` in `src/db/verification_tokens.py` uses `SELECT ... FOR UPDATE` + `flush()` to prevent TOCTOU race conditions on concurrent token redemption. |
| **Voice signature verification** | Dual verification (ECAPA2 192-dim embedding via Modal serverless + OpenAI GPT-4o-transcribe) — no local voice-service container. Transcription scoring runs in-process (word-overlap EN, subsequence+homophone FA). Enrollment: 3 phrases from pool of 200/language → averaged embedding encrypted at rest (Fernet AES-128-CBC + HMAC-SHA256 via `VOICE_ENCRYPTION_KEY`; backward-compatible with unencrypted legacy) and stored as `LargeBinary`; raw audio stored in `enrollment_audio` table for model portability. Verification: 1 random phrase per session start → 30-min session window extended on Submit/Vote/Endorse. Decision matrix: unified thresholds (high sim >=0.45 + standard transcription >=0.65 → accept; moderate sim >=0.38 + strict transcription >=0.75 → accept). Audio duration limits: 1s min, 10s max. Error handling: user-facing messages for duration validation (too short/long); technical error codes V002 (download), V003 (service), V004 (scoring) for pipeline failures. Reject reasons: voice_mismatch, transcript_mismatch, both_mismatch — shown as distinct user messages. Evidence logs scores + phrase_id + reject_reason only (no biometric data). Implementation: `src/voice/`, `modal_functions/voice_embedding.py`. |

### Abuse Thresholds

| Control | Limit |
|---------|-------|
| Submissions per account per day | 5 |
| Accounts per email domain per day | 3 (non-major domains only; major providers exempt) |
| Signups per requester IP per day | 10 |
| Burst quarantine trigger | 3 submissions/5 minutes from one account (soft quarantine: accept + flag for review) |
| Vote changes per cycle | 1 full vote re-submission per cycle (total max: 2 vote submissions/cycle). |
| Failed verification attempts | 5 per email per 24h, then 24h lockout |
| Auth endpoint rate limits | subscribe: 5/min/IP, verify: 10/min/IP, web-session: 5/min/IP (in-process sliding window) |
| Dispute rate limit | 3 disputes per hour per user |
| Voice verification rate limit | 5 attempts per user per hour (enforced before inference) |

### Dispute Handling

- Users flag bad canonicalization or cluster assignment from their dashboard.
- Autonomous dispute-resolution workflow completes within 72 hours (SLA target).
- Resolver can escalate to a stronger model or multi-model ensemble when confidence is low.
- Dispute adjudication must use explicit confidence thresholds with fallback/ensemble paths when below threshold.
- Scope dispute resolution to the disputed submission first (re-canonicalize that item); do not re-run full clustering mid-cycle for a single dispute.
- Disputed items tracked via evidence chain (`dispute_resolved`, optionally `dispute_escalated`) but never removed or suppressed.
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

## Web Authentication Flow

End-to-end login process. All agents modifying auth, deploy, or frontend routing must
understand this flow.

### Signup / Sign-In (Passwordless Magic Link)

```
Browser                    Caddy                 Backend (FastAPI)       Resend API
  │                          │                        │                      │
  │ POST /api/auth/subscribe │                        │                      │
  │─────────────────────────>│ uri strip_prefix /api  │                      │
  │                          │──POST /auth/subscribe─>│                      │
  │                          │                        │─ rate-limit check    │
  │                          │                        │─ create/get user     │
  │                          │                        │─ store magic_link    │
  │                          │                        │  token (15 min)      │
  │                          │                        │──send email─────────>│
  │                          │<──{status, token}──────│                      │
  │<─────────────────────────│                        │                      │
  │ "Check your email"       │                        │                      │
```

### Email Verification → Session Establishment

```
Browser (magic link click)  Caddy                 Backend            NextAuth (web:3000)
  │                          │                        │                    │
  │ GET /{locale}/verify?token=T                      │                    │
  │─────────────────────────>│────────────────────────────────────────────>│
  │                          │                     (Next.js page served)   │
  │                          │                        │                    │
  │ POST /api/auth/verify/T  │                        │                    │
  │─────────────────────────>│ uri strip_prefix /api  │                    │
  │                          │──POST /auth/verify/T──>│                    │
  │                          │                        │─ validate token    │
  │                          │                        │─ mark email_verified│
  │                          │                        │─ create linking_code│
  │                          │                        │  (8 chars, 60 min) │
  │                          │                        │─ create web_session │
  │                          │                        │  code (24ch, 10min)│
  │                          │                        │─ consume magic_link│
  │<─────────{linking_code, email, web_session_code}──│                    │
  │                          │                        │                    │
  │ signIn("credentials", {email, webSessionCode})    │                    │
  │─────────────────────────>│ handle /api/auth/*     │                    │
  │                          │──────────────────────────────────(full path)>│
  │                          │                        │   authorize() calls│
  │                          │                        │<──POST /auth/      │
  │                          │                        │   web-session      │
  │                          │                        │   (internal, via   │
  │                          │                        │   BACKEND_API_     │
  │                          │                        │   BASE_URL)        │
  │                          │                        │─ validate code     │
  │                          │                        │─ verify email match│
  │                          │                        │─ create bearer     │
  │                          │                        │  token (30 days)   │
  │                          │                        │──{access_token}───>│
  │                          │                        │                    │─ store in JWT session
  │<─────────────────────────│<───────────set session cookie───────────────│
  │                          │                        │                    │
  │ router.refresh()         │                        │                    │
  │ (NavBar updates to show email)                    │                    │
```

### Token Types

| Token | Purpose | Expiry | Storage |
|-------|---------|--------|---------|
| `magic_link` | Email verification URL | 15 min | `verification_tokens` DB table |
| `linking_code` | Telegram account linking | 60 min | `verification_tokens` DB table |
| `web_session` | One-time code exchanged for bearer token | 10 min | `verification_tokens` DB table |
| Bearer (access) token | Authenticated API access | 30 days | Signed with `WEB_ACCESS_TOKEN_SECRET` (HMAC-SHA256), stored in NextAuth JWT cookie |

### Caddy Routing for `/api/auth/*`

The `/api/auth/*` namespace is split between two services:

- **Backend** (FastAPI): `/api/auth/subscribe`, `/api/auth/verify/*`, `/api/auth/web-session`
- **Web** (NextAuth): all other `/api/auth/*` (session, callback, csrf, etc.)

Use `handle` + `uri strip_prefix /api` for backend routes. **Never use `handle_path`** for
these — it strips the entire matched prefix, breaking the backend routing.
NextAuth routes keep their full `/api/auth/...` path (no stripping).

### Server-Side vs Client-Side API Base

| Context | Environment variable | Resolved value |
|---------|---------------------|----------------|
| Client-side (browser JS) | `NEXT_PUBLIC_API_BASE_URL` (build-time) | `/api` → goes through Caddy |
| Server-side (NextAuth authorize) | `BACKEND_API_BASE_URL` (runtime) | `http://backend:8000` → direct container network |
| Server-side (SSR pages, ops) | `BACKEND_API_BASE_URL` via `resolveApiBase()` | `http://backend:8000` → direct container network |

The `web/lib/api.ts` helper auto-selects: `BACKEND_API_BASE_URL` on the server,
`NEXT_PUBLIC_API_BASE_URL` in the browser.

### Ops Console Access

- Same bearer-token auth as dashboard — no separate admin credentials
- Staging: `OPS_CONSOLE_REQUIRE_ADMIN=false` (any authenticated user)
- Production: `OPS_CONSOLE_REQUIRE_ADMIN=true` + `OPS_ADMIN_EMAILS` list
- Feature-flagged via `OPS_CONSOLE_ENABLED` and `OPS_CONSOLE_SHOW_IN_NAV`

### NavBar Session Awareness

The server layout calls `auth()` and passes `userEmail` to NavBar as a prop.
When logged in: shows user email. When not: shows "Sign Up" button.
After verification, `router.refresh()` re-renders the server layout to update NavBar.

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
bot_state: str | None               # Current interaction state (e.g., "awaiting_submission", "voting", "choosing_voice_lang", "enrolling_voice", "awaiting_voice")
bot_state_data: dict | None         # JSONB — session data for multi-step flows (e.g., voting progress, enrollment state)
voice_enrolled_at: datetime | None  # When voice enrollment was completed
voice_verified_at: datetime | None  # Last successful voice verification (session expires after 30 min)
voice_embedding: bytes | None       # 192-dim ECAPA-TDNN float32 embedding (Fernet-encrypted when VOICE_ENCRYPTION_KEY is set; raw BYTEA otherwise)
voice_model_version: str | None     # SpeechBrain model version (detect embedding space mismatches)
```

Properties:
- `is_voice_enrolled` → True if `voice_enrolled_at` and `voice_embedding` are set
- `is_voice_session_active` → True if `voice_verified_at` within `VOICE_SESSION_DURATION_MINUTES` (default 30)

### Submission

```
id: UUID
user_id: UUID
raw_text: str
language: str
status: "pending" | "canonicalized" | "processed" | "quarantined" | "flagged" | "rejected"
processed_at: datetime | None
hash: str                           # SHA-256 of raw_text
created_at: datetime
evidence_log_id: int
```

### PolicyCandidate

```
id: UUID
submission_id: UUID
title: str                          # 5-15 words, always English
summary: str                        # 1-3 sentences, always English
stance: "support" | "oppose" | "neutral" | "unclear"  # "unclear" = model uncertainty; "neutral" = descriptive/no explicit side
policy_topic: str                   # Stance-neutral umbrella topic (e.g., "internet-censorship"), lowercase-with-hyphens
policy_key: str                     # Stance-neutral ballot-level discussion (e.g., "political-internet-censorship"), lowercase-with-hyphens
entities: list[str]
embedding: list[float]              # pgvector column
confidence: float                   # 0-1
ambiguity_flags: list[str]
model_version: str
prompt_version: str
created_at: datetime
evidence_log_id: int
```

### Cluster

```
id: UUID
policy_topic: str                   # Stance-neutral umbrella topic (e.g., "internet-censorship")
policy_key: str                     # Stance-neutral ballot-level key (partial unique index where status='open')
status: str                         # "open" (active) or "archived" (voted on, frozen)
summary: str                        # English (canonical language; base fields are always English)
ballot_question: str | None         # Stance-neutral English ballot question for endorsement step
ballot_question_fa: str | None      # Farsi ballot question
candidate_ids: list[UUID]
member_count: int
approval_count: int
needs_resummarize: bool             # True when cluster needs ballot question (re)generation
last_summarized_count: int          # member_count at last summarization (for growth detection)
created_at: datetime
evidence_log_id: int
```

Cluster lifecycle: `open` → `archived` (when included in a voting cycle via `open_cycle()`). New submissions with the same `policy_key` create a fresh open cluster. Only open clusters are processed by the pipeline (summarization, ballot questions, options, agenda, normalization, key merges) and shown in the Telegram endorsement flow.

### Vote

```
id: UUID
user_id: UUID
cycle_id: UUID
approved_cluster_ids: list[UUID]    # Derived from selections when present; kept for backward compatibility
selections: list[dict] | None       # JSONB — per-policy stance selections [{cluster_id, option_id}, ...]
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

### PolicyOption

```
id: UUID
cluster_id: UUID                    # FK to clusters
position: int                       # 1-based display order
label: str                          # Farsi label (e.g., "حمایت از این سیاست")
label_en: str | None                # English label
description: str                    # Farsi — concrete trade-offs, pros & cons
description_en: str | None          # English description
model_version: str                  # LLM model that generated the option
created_at: datetime
evidence_log_id: int | None
```

Generated by `src/pipeline/options.py` after cluster summarization. Each cluster receives 2–4 distinct stance options. Option generation first attempts JSON salvage/repair of wrapped responses before escalating to the explicit fallback model; generic support/oppose fallback is reserved for genuine model/infrastructure failure after those attempts.

### VotingCycle

```
id: UUID
started_at: datetime
ends_at: datetime
status: "active" | "closed" | "tallied"
cluster_ids: list[UUID]
results: list[{cluster_id, approval_count, approval_rate, option_counts?}] | None
total_voters: int
evidence_log_id: int
```

### EvidenceLogEntry

```
id: int (BIGSERIAL)
timestamp: datetime
event_type: str                     # See valid event types below
entity_type: str
entity_id: UUID
payload: dict                       # JSONB — enriched with human-readable context (see Evidence Payload Enrichment)
hash: str                           # SHA-256(canonical JSON of {timestamp,event_type,entity_type,entity_id,payload,prev_hash})
prev_hash: str                      # previous entry's hash (chain)
```

Valid event types (defined by `EVENT_CATALOG` in `src/db/evidence.py`):
```
# Submission lifecycle
submission_received, submission_not_eligible, submission_rate_limited,
submission_rejected_not_policy,
# Candidate lifecycle
candidate_created,
# Cluster lifecycle
cluster_created, cluster_updated, cluster_merged,
ballot_question_generated, policy_options_generated,
# Endorsement lifecycle
policy_endorsed, endorsement_not_eligible,
# Voting lifecycle
vote_cast, vote_not_eligible, vote_change_limit_reached,
cycle_opened, cycle_closed,
# Identity
user_verified,
# Disputes
dispute_escalated, dispute_resolved, dispute_metrics_recorded,
dispute_tuning_recommended,
# Anchoring
anchor_computed, anchor_publish_attempted, anchor_publish_succeeded,
anchor_publish_failed, audit_bundle_generated, audit_bundle_publish_succeeded,
audit_bundle_publish_failed,
# Voice
voice_enrolled, voice_enroll_phrase_rejected, voice_verified
# Pipeline degradation (fallback visibility)
submission_deferred_to_batch, candidate_parse_repaired,
normalization_step_failed, ballot_generation_failed,
policy_options_fallback_used, dispute_ensemble_member_failed
```

### IPSignupLog (operational — `src/db/ip_signup_log.py`)

```
id: int (BIGSERIAL)
requester_ip: str               # IPv4/IPv6, max 45 chars
email_domain: str               # Domain portion of signup email
created_at: datetime             # server_default=now()
```

DB-backed IP rate-limiting table. Replaces the former in-memory `_IP_SIGNUP_COUNTER` / `_IP_DOMAIN_TRACKER` dicts. Queried by `check_signup_ip_rate()` and `check_signup_domain_diversity_by_ip()` in `src/handlers/abuse.py`. Written to by `record_account_creation_velocity()`. Indexes: composite `(requester_ip, created_at)` for rate-window lookups, `(created_at)` for periodic cleanup.

### Evidence Payload Enrichment

All `append_evidence` payloads include human-readable context so the evidence chain is self-describing. Key fields per event type:

| Event type | Required payload fields |
|---|---|
| `submission_received` | `submission_id`, `user_id`, `raw_text`, `language`, `status`, `hash` (or `status`+`reason_code` for PII rejections) |
| `submission_not_eligible` | `user_id`, `reason_code` |
| `submission_rate_limited` | `user_id`, `reason_code`, `limit_type` |
| `submission_rejected_not_policy` | `submission_id`, `rejection_reason`, `model_version`, `prompt_version` |
| `candidate_created` | `submission_id`, `title`, `summary`, `stance`, `policy_topic`, `policy_key`, `confidence`, `model_version`, `prompt_version` |
| `cluster_updated` | `cluster_id`, `policy_key`, `old_member_count`, `new_member_count` |
| `cluster_merged` | `survivor_key`, `merged_key`, `merged_cluster_id`, `new_member_count` |
| `ballot_question_generated` | `policy_key`, `ballot_question`, `member_count`, `model_version` |
| `vote_cast` | `user_id`, `cycle_id`, `approved_cluster_ids`, `selections` (when per-policy voting) |
| `vote_not_eligible` | `user_id`, `cycle_id`, `reason_code` |
| `vote_change_limit_reached` | `user_id`, `cycle_id` |
| `policy_endorsed` | `user_id`, `cluster_id` |
| `endorsement_not_eligible` | `user_id`, `cluster_id`, `reason_code` |
| `policy_options_generated` | `cluster_id`, `option_count`, `labels` |
| `cycle_opened` | `cycle_id`, `cluster_ids`, `starts_at`, `ends_at`, `cycle_duration_hours` |
| `cycle_closed` | `total_voters`, `results` |
| `user_verified` | `user_id`, `method` |
| `dispute_resolved` | `submission_id`, `candidate_id`, `escalated`, `confidence`, `model_version`, `resolved_title`, `resolved_summary`, `resolution_seconds` |
| `dispute_escalated` | `threshold`, `primary_model`, `primary_confidence`, `ensemble_models`, `selected_model`, `selected_confidence` |
| `anchor_publish_attempted` | `day`, `merkle_root`, `provider` |
| `anchor_publish_succeeded` | `day`, `merkle_root`, `provider`, `status`, `ots_proof_path` |
| `anchor_publish_failed` | `day`, `merkle_root`, `provider`, `status`, `error_type` |
| `audit_bundle_generated` | `day`, `entry_count`, `bundle_sha256`, `storage_path` |
| `audit_bundle_publish_succeeded` | `day`, `bundle_sha256`, `manifest_path`, `index_path` |
| `audit_bundle_publish_failed` | `day`, `bundle_sha256`, `error_type` |
| `submission_deferred_to_batch` | `submission_id`, `error_type`, `error_message` |
| `candidate_parse_repaired` | `submission_id`, `repair_method` (`regex` or `llm`) |
| `normalization_step_failed` | `cluster_key`, `error_type`, `error_message` |
| `ballot_generation_failed` | `cluster_id`, `policy_key`, `error_type`, `error_message` |
| `policy_options_fallback_used` | `cluster_id`, `policy_key`, `error_type`, `error_message` |
| `dispute_ensemble_member_failed` | `submission_id`, `model`, `error_type`, `error_message` |

### Evidence PII Stripping & Visibility Tiers

The public `GET /analytics/evidence` endpoint applies two layers of payload redaction:
1. **Recursive PII stripping** (`strip_evidence_pii()`) — removes `user_id`, `email`, `account_ref`, `wa_id` from payloads at any nesting level (top-level, nested dicts, list items)
2. **Visibility-tier filtering** (`apply_visibility_tier()`) — per-event-type delayed fields (e.g., `vote_cast` selections) are hidden while the associated voting cycle is active, and revealed after the cycle closes

- `raw_text` is preserved (it's the civic concern, not PII)
- Internal evidence entries retain `user_id` for audit integrity; it's only stripped from the public API response
- This supports coercion resistance: no transferable proof linking a user to a specific action

### User Receipts

Receipt-eligible events (`policy_endorsed`, `vote_cast`) generate HMAC-SHA256 receipt tokens:
- `generate_receipt_token(entry_hash, signing_key)` creates a stateless proof of inclusion
- Users retrieve their receipts at `GET /user/dashboard/receipts` (bearer-authenticated)
- Receipt verification is stateless: `verify_receipt_token(entry_hash, key, token)` recomputes and compares
- Receipts prove a user's action was recorded in the chain without revealing their identity publicly
- Signing key: `WEB_ACCESS_TOKEN_SECRET` (backend-only)

### Evidence API Contract

- `GET /analytics/evidence` — paginated, with `entity_id`, `event_type`, `page`, `per_page` query params; returns `{total, page, per_page, entries}` with visibility-tier-aware payload redaction
- `GET /analytics/evidence/verify` — server-side chain verification; returns `{valid, entries_checked}`
- `GET /user/dashboard/receipts` — authenticated; returns user's receipt-eligible evidence entries with `receipt_token` HMAC
- `GET /user/dashboard/receipts/{entry_hash}/verify` — authenticated; returns `{status, receipt_valid, entry_found, bundle_day, included_in_public_bundle, bundle_hash_matches_manifest, ots_proof_present, ots_verified, verified_before, download_urls}` for the user's receipt entry
- `/{locale}/my-activity` now includes a receipts section with verification status chips and links to receipt detail pages
- `/{locale}/my-activity/receipts/{entryHash}` shows plain-language verification status, trust-language guardrails, technical details, and live proof-download links
- `GET /analytics/audit-bundles` — public; lists daily bundle summaries from `audit/index.json`
- `GET /analytics/audit-bundles/{day}` — public; returns manifest summary, timestamping metadata, and download links
- `GET /analytics/audit-bundles/{day}/proof?entry_hash=...` — public; returns inclusion result and proof metadata for a given entry hash
- `GET /analytics/audit-bundles/{day}/bundle` — public raw bundle download
- `GET /analytics/audit-bundles/{day}/manifest` — public raw manifest download
- `GET /analytics/audit-bundles/{day}/ots` — public raw OpenTimestamps proof download when present
- `/{locale}/collective-concerns/audit-bundles` lists public audit snapshots
- `/{locale}/collective-concerns/audit-bundles/{day}` shows one day’s public audit snapshot details and artifact links
- Frontend evidence explorer uses server-side verify (no client-side hash recomputation); deep links to analytics pages via `entityLink()`

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async), Pydantic |
| **Database** | PostgreSQL 15+ with pgvector extension |
| **Website** | Next.js (App Router), TypeScript, Tailwind CSS, next-intl |
| **Dependency mgmt** | uv (Python), npm (Node) |
| **Migrations** | Alembic |
| **Testing** | pytest (Python), vitest or jest (TypeScript) |
| **Linting** | ruff (Python), eslint (TypeScript) |
| **Type checking** | mypy strict (Python) |
| **Transactional email** | Resend (REST API via httpx). Default from: `onboarding@resend.dev`; switch to `noreply@collectivewill.org` when DNS verified. Console fallback when `RESEND_API_KEY` unset. |
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
│   │   ├── base.py              # Abstract channel interface (+ download_file abstract method)
│   │   ├── telegram.py          # Telegram Bot API client (+ voice parsing, file download)
│   │   ├── whatsapp.py          # Evolution API client (post-MVP; download_file stub)
│   │   └── types.py             # Unified message format (+ callback, reply_markup, voice_file_id, voice_duration)
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── intake.py            # Receives submissions
│   │   ├── voting.py            # Vote prompts, receives votes
│   │   ├── notifications.py     # Sends updates
│   │   ├── identity.py          # Email magic-link, WhatsApp linking
│   │   ├── abuse.py             # Rate limiting, quarantine
│   │   └── commands.py          # Message command router (+ voice gate, enrollment/verification handlers)
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── llm.py               # LLM abstraction + router
│   │   ├── privacy.py           # Strip metadata for LLM
│   │   ├── canonicalize.py      # LLM canonicalization + policy_topic/policy_key assignment
│   │   ├── embeddings.py        # Embedding computation
│   │   ├── cluster.py           # Policy-key grouping + centroid computation
│   │   ├── normalize.py         # Hybrid embedding + LLM key normalization (cross-topic)
│   │   ├── endorsement.py       # Ballot question generation per policy_key
│   │   ├── summarize.py         # Cluster summaries (legacy)
│   │   ├── options.py           # LLM-generated per-policy stance options
│   │   └── agenda.py            # Agenda building
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── client.py            # VoiceCloudClient — orchestrates OpenAI transcription + Modal embedding
│   │   ├── transcription.py     # OpenAI GPT-4o-transcribe API client
│   │   ├── embedding.py         # Modal serverless embedding API client
│   │   ├── transcription_scoring.py  # Word-overlap (EN) and subsequence+homophone (FA) scoring
│   │   ├── audio.py             # Audio download + duration validation
│   │   ├── phrases.py           # 200 phrases per language (fa/en), selection
│   │   ├── scoring.py           # Cosine similarity, decision matrix, embedding serialization
│   │   ├── enrollment.py        # Multi-step enrollment state machine (stores audio for portability)
│   │   ├── verification.py      # Session verification against stored embedding
│   │   ├── crypto.py            # Fernet encryption/decryption for voice embeddings at rest
│   │   └── errors.py            # Voice error codes (V002–V004) for pipeline failure diagnosis
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── submission.py
│   │   ├── cluster.py
│   │   ├── vote.py
│   │   ├── endorsement.py
│   │   ├── enrollment_audio.py  # Raw enrollment audio storage for model portability
│   │   └── policy_option.py     # LLM-generated stance options per cluster
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── evidence.py          # Evidence store operations
│   │   ├── queries.py
│   │   ├── sealed_mapping.py    # SealedAccountMapping ORM (platform_id ↔ account_ref)
│   │   ├── verification_tokens.py # VerificationToken ORM (magic links, linking codes, web sessions)
│   │   ├── ip_signup_log.py     # IPSignupLog ORM (DB-backed IP rate limiting)
│   │   ├── anchoring.py         # DailyAnchor ORM (Merkle root)
│   │   └── heartbeat.py         # SchedulerHeartbeat ORM
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
│   │       └── request_context.py
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
├── modal_functions/
│   └── voice_embedding.py       # Modal serverless function: ECAPA2 speaker embedding
├── docker-compose.yml
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

---

## What's In Scope (v0)

- Telegram submission intake (official Bot API) for MVP build/testing
- Button-only Telegram UX (inline keyboards, no typed commands — reduces misinterpretation)
- Email magic-link verification
- Messaging account linking with opaque account refs (Telegram now; WhatsApp mapping path prepared)
- Canonicalization (Claude Sonnet, cloud, inline at submission time with batch fallback; always outputs English)
- Garbage rejection (LLM detects invalid submissions, rejects with user-language feedback; garbage counts against daily quota)
- Embeddings (quality-first cloud model in v0; computed inline after canonicalization)
- Clustering (LLM-driven policy-key grouping, batch on hybrid trigger: `BATCH_THRESHOLD` unprocessed submissions OR `PIPELINE_INTERVAL_HOURS` max interval)
- LLM-generated per-policy stance options (2–4 options per cluster via `pipeline/options.py`)
- Pre-ballot endorsement/signature stage for cluster qualification
- Per-policy stance voting via Telegram (paginated one-policy-at-a-time flow with summary review)
- Public analytics dashboard (no login wall)
- User dashboard (submissions, votes, disputes)
- Evidence store (hash-chain in Postgres)
- Farsi + English UI (RTL support)
- Audit evidence explorer
- FAQ page (`/faq`) with safety, privacy, and how-it-works content (bilingual EN/FA)
- Ops observability console (`/ops`) for redacted runtime diagnostics in dev/staging, with optional admin-only production mode
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
- Public/anonymous access to raw runtime or Docker/container logs

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
