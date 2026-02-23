# Task: Ops Debug Console

## Depends on
- `website/01-nextjs-setup-i18n` (routing, shared layout, i18n)
- `website/03-auth-magic-links` (authentication primitives)
- `website/08-audit-evidence-explorer` (public audit surface that must remain separate)

## Goal
Add an operations-facing diagnostics console at `/ops` so developers/operators can see runtime health, recent errors, and system action flow without tailing container logs manually.

The console is distinct from public audit transparency:
- `/analytics/evidence` stays public and trust-focused.
- `/ops` is operational and environment-gated.

## Files to create/modify

- `web/app/[locale]/ops/page.tsx` - ops page
- `web/components/OpsHealthPanel.tsx` - service health cards
- `web/components/OpsEventFeed.tsx` - recent event/error feed
- `web/components/NavBar.tsx` - conditional `Ops` tab
- `web/messages/fa.json` - add ops translations
- `web/messages/en.json` - add ops translations
- `src/api/routes/ops.py` - ops endpoints
- `src/api/routes/__init__.py` - include ops router

## Specification

### Access model

- Dev/staging: `/ops` can be visible in top navigation.
- Production: `/ops` must be hidden unless enabled by feature flag and protected by admin auth.
- No anonymous access in production.

Recommended config:
- `OPS_CONSOLE_ENABLED` (bool)
- `OPS_CONSOLE_SHOW_IN_NAV` (bool)
- `OPS_CONSOLE_REQUIRE_ADMIN` (bool, default true in production)

### What the page shows

1. **Health summary**
   - API health
   - DB health
   - Scheduler status (last run / next run if available)
   - Telegram webhook status
   - Email transport status

2. **Recent errors**
   - Last N errors with timestamp, component, level, message, request/run correlation id

3. **Recent operational events**
   - Key lifecycle events across auth, webhook intake, pipeline, voting, and email
   - Filter by event type, level, and time window

4. **Background jobs**
   - Last run status, duration, and failure reason for pipeline/scheduler jobs

### API contracts

Create backend endpoints under `/ops`:

- `GET /ops/status`
  - Returns health and subsystem status summary
- `GET /ops/events?limit=100&level=error|warning|info&type=...`
  - Returns recent structured events/errors
- `GET /ops/jobs`
  - Returns recent scheduler/pipeline run outcomes

All responses must be sanitized and typed.

### Data source policy

- Do not stream raw `docker compose logs` directly to the browser.
- Use structured application events/log records, redacted at write-time and read-time.
- Include correlation ids so one user flow can be traced across API + workers.

## Constraints

- Never expose secrets, tokens, raw platform ids, email addresses, or request bodies with PII in ops responses.
- Keep `/ops` separate from adjudication decisions. It can show state, but must not introduce per-item manual approve/reject actions for votes, disputes, or quarantine outcomes.
- Keep public audit page unchanged in trust semantics (no auth wall and client-verifiable chain checks remain intact).
- Feature-flag the entire surface so production rollout is explicit.

## Tests

Write tests covering:

- `/ops` nav link appears only when config allows
- Production mode without admin auth cannot access `/ops`
- `GET /ops/status` returns expected health keys
- `GET /ops/events` filtering works by level/type
- PII redaction in ops payloads (email, tokens, raw platform ids are absent/masked)
- Ops page renders health cards and event list in Farsi and English
