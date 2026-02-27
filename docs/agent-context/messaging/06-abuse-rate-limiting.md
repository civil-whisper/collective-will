# Task: Abuse Controls and Rate Limiting

## Depends on
- `database/03-core-models` (User, Submission models)
- `database/02-db-connection` (session)

## Goal
Implement rate limiting, burst detection, and quarantine logic as reusable functions that handlers call before processing.

## Files

- `src/handlers/abuse.py` — rate limiting and quarantine logic
- `src/db/ip_signup_log.py` — `IPSignupLog` ORM model for DB-backed IP rate limiting
- `migrations/versions/003_ip_signup_log.py` — creates `ip_signup_log` table

## Specification

### IP signup tracking (DB-backed)

IP-based signup rate limits and domain-diversity telemetry are backed by the
`ip_signup_log` table (not in-memory counters). Each signup records `(requester_ip,
email_domain, created_at)`. Rate checks query this table with indexed lookups.

The `requester_ip` is extracted server-side by `_get_client_ip()` in
`src/api/routes/auth.py` from `X-Forwarded-For` (first hop) or `request.client.host`.
It is **not** supplied by the client request body.

```sql
-- ip_signup_log indexes
ix_ip_signup_log_ip_created_at (requester_ip, created_at)  -- rate-window lookups
ix_ip_signup_log_created_at    (created_at)                 -- periodic cleanup
```

### Rate limit checks

All functions are async and take a database session + user/identifier.

```python
async def check_submission_rate(db: AsyncSession, user_id: UUID) -> RateLimitResult:
    """Check if user can submit. Returns allowed=True or reason for denial."""

async def check_domain_rate(db: AsyncSession, email_domain: str) -> RateLimitResult:
    """Check non-major email domain hasn't exceeded MAX_SIGNUPS_PER_DOMAIN_PER_DAY."""

def is_major_email_provider(email_domain: str, major_list: set[str]) -> bool:
    """Return True when domain is exempt from per-domain signup cap."""

async def check_signup_ip_rate(
    db: AsyncSession,
    requester_ip: str,
) -> RateLimitResult:
    """Check requester IP hasn't exceeded MAX_SIGNUPS_PER_IP_PER_DAY.
    Queries ip_signup_log WHERE requester_ip = ? AND created_at >= (now - 24h)."""

async def check_signup_domain_diversity_by_ip(
    db: AsyncSession,
    requester_ip: str,
) -> RateLimitResult:
    """Detect anomalous distinct email-domain count from one IP in 24h.
    Queries ip_signup_log for COUNT(DISTINCT email_domain).
    v0 behavior: flag only (telemetry), do not block automatically."""

async def score_disposable_email_domain(email_domain: str) -> float:
    """Return trust-score adjustment for disposable domains (soft signal only)."""

async def check_burst(db: AsyncSession, user_id: UUID) -> RateLimitResult:
    """Check if user exceeds burst threshold from settings. Triggers soft quarantine."""

async def check_vote_change(db: AsyncSession, user_id: UUID, cycle_id: UUID) -> RateLimitResult:
    """Allow one full vote re-submission per cycle; block additional changes."""

async def record_account_creation_velocity(
    db: AsyncSession,
    requester_ip: str | None,
    email_domain: str,
) -> None:
    """Record signup event to ip_signup_log for DB-backed rate limiting."""
```

### RateLimitResult

```python
class RateLimitResult(BaseModel):
    allowed: bool
    reason: str | None = None    # Human-readable reason if denied
    quarantine: bool = False     # True if this check triggers quarantine
```

### Thresholds (from frozen decisions)

| Check | Threshold | Window |
|-------|-----------|--------|
| Submissions per user | 5 | 24 hours |
| Accounts per email domain | 3/day for non-major domains only | 24 hours |
| Signups per requester IP | 10/day (hard block) | 24 hours |
| Distinct signup domains per requester IP | Track and flag anomalies (no auto-block in v0) | 24 hours |
| Disposable-email domain detection | Soft trust-score signal (no auto-block in v0) | N/A |
| Account-creation velocity metrics | Log/monitor only | Rolling |
| Burst detection | `BURST_QUARANTINE_THRESHOLD_COUNT` (default 3, soft quarantine) | `BURST_QUARANTINE_WINDOW_MINUTES` (default 5) |
| Vote changes per cycle | 1 full re-submission (total max 2 vote submissions) | Per voting cycle |
| Failed verifications | 5 | 24 hours |

### Quarantine

When burst detection triggers (soft quarantine):
1. Set a `quarantined_at` timestamp on the user (add this field to User model if needed)
2. Incoming submissions are still accepted but stored with `status="quarantined"` for review
3. Quarantined submissions are NOT processed by the main pipeline until automated adjudication runs
4. User receives a message indicating temporary review status (not permanent denial)
5. Enter-quarantine and release decisions are logged to evidence store with policy inputs and outcome

### Unquarantine

Unquarantine is automated by policy-driven rules (for example, cooldown elapsed + low-risk signals). No manual per-account unquarantine path.

## Constraints

- Rate limit queries must be efficient — use indexed timestamp columns and COUNT queries, not loading all rows.
- Do NOT use in-memory rate limiting (Redis, etc.). Query the database directly. At v0 scale this is fine.
- Quarantine does not delete any data. Submissions are preserved but held.
- Rate limit messages to users should be in Farsi.
- Major provider domains are exempt from domain cap.
- Per-IP signup cap is a blocking control in v0 (not telemetry-only).
- Burst soft-quarantine thresholds must come from settings, not hardcoded values.
- Signup-domain diversity by IP and disposable-domain checks are v0 telemetry/signals; they should not hard-block subscription by themselves.
- Quarantine adjudication must be autonomous; humans can tune thresholds/policies but do not resolve individual quarantined users.
- Every quarantine adjudication action (enter, hold, release) must be evidence-logged.

## Tests

Write tests in `tests/test_handlers/test_abuse.py` covering:
- `check_submission_rate`: allows 5 submissions, denies 6th
- `check_submission_rate`: resets after 24 hours (submissions from yesterday don't count)
- `check_domain_rate`: allows 3 accounts on same non-major domain, denies 4th
- `check_domain_rate`: major providers are exempt from domain cap
- `check_signup_ip_rate`: allows up to configured cap, denies above cap
- `check_signup_domain_diversity_by_ip`: high distinct-domain count from one IP is flagged (allowed=False must NOT be used for this in v0)
- `score_disposable_email_domain`: known disposable domain produces negative trust adjustment
- `check_burst`: 3 submissions in 5 minutes triggers soft quarantine
- `check_burst`: 2 submissions in 5 minutes does not trigger
- `check_vote_change`: first full vote re-submission allowed, second denied
- Quarantined user's submissions are stored with `status="quarantined"`
- Automated adjudication can release quarantine when policy conditions are met
- Quarantine enter/release decisions are evidence-logged with adjudication trace
- `record_account_creation_velocity` emits metrics with ip/domain dimensions
- RateLimitResult correctly reports reason and quarantine flag
- Rate limit functions handle empty database (no prior submissions) gracefully
