# Decision Rationale: Staging Debug Sprint

## Context

All core systems (Telegram bot, web frontend, backend API, pipeline, evidence store)
are architecturally complete and tested in CI. The next step is real-user end-to-end
testing on the staging environment with a small group of friends before wider rollout.

Several implementation gaps and overly-strict production defaults block this:

1. **In-memory sealed mapping** — Telegram `chat_id ↔ account_ref` mapping lives in
   Python module-level dicts (`_SEALED_TG_MAPPING` / `_REVERSE_TG_MAPPING`). Any
   backend restart loses all Telegram account links. The original implementation
   contract (`messaging/09-telegram-test-channel.md`) specifies a `MappingRepository`
   with database persistence, but the implementation took a shortcut.

2. **In-memory auth tokens** — Magic links (`_PENDING_MAGIC_LINKS`), linking codes
   (`_PENDING_LINKING_CODES`), and failed-verification tracking (`_FAILED_VERIFICATIONS`)
   in `src/handlers/identity.py` are all in-memory dicts. Restart kills all pending
   sign-up flows. Background tasks may run in separate contexts where these dicts are
   not shared.

3. **Hardcoded production guards** — Several thresholds that are appropriate for
   production are too restrictive for a small staging test:
   - 48-hour account age before submit/vote (blocks testing for 2 days after signup)
   - 48-hour voting cycle duration (too long to see results during a test session)
   - `min_cluster_size=5` (need 5+ similar submissions before any cluster forms)
   - `min_preballot_endorsements=5` (need 5 endorsement signatures before ballot)
   - `contribution_count >= 1` hardcoded vote-eligibility check (no config override)
   - `submissions_per_day=5` hardcoded (no config override)

## Decisions

### D1: Persist sealed mapping to database

Add a `sealed_account_mappings` table:

```
id: UUID
platform: "telegram" | "whatsapp"
platform_id: str  (encrypted or hashed chat_id / wa_id)
account_ref: str  (opaque UUIDv4)
created_at: datetime
```

Replace the in-memory dicts in `telegram.py` (and `whatsapp.py`) with async DB
lookups through this table. This aligns with the original contract in
`messaging/09-telegram-test-channel.md` which specified `MappingRepository`.

The `platform_id` column stores the raw identifier. In production this column should
be encrypted at rest; for staging, plain storage is acceptable. The column must never
appear in logs, API responses, or exports.

### D2: Persist auth tokens to database

Add a `verification_tokens` table:

```
id: UUID
token: str (indexed, unique)
email: str
token_type: "magic_link" | "linking_code"
created_at: datetime
expires_at: datetime
used: bool (default false)
```

Replace `_PENDING_MAGIC_LINKS` and `_PENDING_LINKING_CODES` dicts with DB operations.
Failed-verification tracking moves to a `failed_verifications` counter column on the
user record or a separate lightweight table.

### D3: Make all guards config-backed

Every threshold that affects staging testability must be overridable via environment
variable. New config fields in `Settings`:

| Field | Env var | Prod default | Staging override |
|-------|---------|-------------|-----------------|
| `voting_cycle_hours` | `VOTING_CYCLE_HOURS` | `48` | `1` |
| `max_submissions_per_day` | `MAX_SUBMISSIONS_PER_DAY` | `5` | `50` |
| `require_contribution_for_vote` | `REQUIRE_CONTRIBUTION_FOR_VOTE` | `true` | `false` |

Already config-backed (just need staging values):

| Field | Env var | Prod default | Staging override |
|-------|---------|-------------|-----------------|
| `min_account_age_hours` | `MIN_ACCOUNT_AGE_HOURS` | `48` | `0` |
| `min_cluster_size` | `MIN_CLUSTER_SIZE` | `5` | `2` |
| `min_preballot_endorsements` | `MIN_PREBALLOT_ENDORSEMENTS` | `5` | `1` |

### D4: Add Telegram webhook registration helper

Add a management command or script that calls the Telegram `setWebhook` API to
register the staging webhook URL. This avoids manual curl commands.

### D5: Staging `.env` security

The `deploy/.env.staging` file currently contains real API keys committed to the
repository. These keys must be rotated and the file must be moved to server-only
storage or a secrets manager. The committed version should contain only placeholder
values (like `.env.example`).

## Guardrails

- Production defaults remain unchanged. Staging overrides are **only** via env vars.
- The `sealed_account_mappings` table follows the same privacy rules as the existing
  WhatsApp sealed mapping: raw platform IDs never appear in logs, API responses, or
  evidence store payloads.
- Auth token persistence does not change the security model: tokens still expire,
  lockout rules still apply, `secrets` module is still used for generation.
- Guard relaxation is staging-only. The config defaults in code remain at production
  values. Only the staging `.env` overrides them.
