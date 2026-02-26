# Task: Audit Evidence Explorer

## Depends on
- `website/01-nextjs-setup-i18n` (Next.js project with i18n)
- `database/04-evidence-store` (evidence API + PII stripping)

## Goal
Build a public evidence chain explorer that lets users verify system integrity and understand what happened at each step. Every evidence entry maps to a human-readable action with deep links back to analytics.

## Implementation (Done)

### Architecture

Single client component at `web/app/[locale]/analytics/evidence/page.tsx` ("use client").

Key libraries:
- `web/lib/evidence.ts` — types, `eventDescription()`, `entityLink()`, `relativeTime()`, filter helpers, `canonicalJson()`, `verifyChain()` (client-side, retained for offline use)
- `web/messages/{en,fa}.json` — i18n keys under `analytics.events.*` namespace

### Evidence page (`/analytics/evidence`)

A public page (no auth required) with:

1. **Chain status badge** (`ChainStatusBadge`) — green valid / red broken / gray unverified
2. **Verify button** — calls server-side `GET /analytics/evidence/verify` (not client-side hash recomputation)
3. **Category filter pills** — Submissions, Policies, Votes, Disputes, Users, System
4. **Smart default filter** — deliberation events only by default (toggle to show all)
5. **Search** — filters by entity_id, event_type, hash, or event description text
6. **Entity filter** — `?entity=UUID` query param for deep linking from analytics pages
7. **Paginated evidence list** — collapsible cards, 50 per page

### Evidence entry cards

Each card shows:
- **Event type pill** (e.g., "submission received", "vote cast")
- **Human-readable description** via `eventDescription()` — e.g., `Submission received: "Concern about roads"`, `Vote cast: approved 3 policies`
- **Relative timestamp** (e.g., "2h ago")
- **Expandable details** (click to toggle):
  - Key-value payload fields (Domain, Confidence, Status, Language, Model, etc.)
  - Original text (if `raw_text` present in payload)
  - Full payload JSON (collapsible `<details>`)
  - Hash chain footer (hash, prev_hash, entity_id, timestamp) with copy button
  - "View in Analytics" deep link (for clusters → cluster detail, votes → top policies)

### Event descriptions (i18n)

`eventDescription()` in `web/lib/evidence.ts` maps each event type to a human-readable string using `next-intl` translations. Keys are under `analytics.events.*` in both `en.json` and `fa.json`. Template variables (e.g., `{text}`, `{title}`, `{count}`) are interpolated.

### Deep links

- **From evidence to analytics**: `entityLink()` maps entity types to analytics pages (cluster → cluster detail, voting_cycle/vote → top policies)
- **From analytics to evidence**: Cluster detail page and top policies page have "Audit Trail" links that navigate to `/analytics/evidence?entity=UUID`

### API contract

- `GET /analytics/evidence` — returns `{total, page, per_page, entries}` with PII-stripped payloads, **newest first** (ordered by `id DESC`)
- `GET /analytics/evidence/verify` — server-side chain verification; returns `{valid, entries_checked}`
- Query params: `entity_id` (UUID), `event_type` (string), `page` (int), `per_page` (int, max 200)

### Filter categories

Defined in `EVENT_CATEGORIES` in `web/lib/evidence.ts`:

| Category | Event types |
|---|---|
| Submissions | `submission_received`, `submission_rejected_not_policy` |
| Policies | `candidate_created`, `cluster_created`, `cluster_updated`, `cluster_merged`, `ballot_question_generated`, `policy_options_generated` |
| Votes | `vote_cast`, `policy_endorsed`, `cycle_opened`, `cycle_closed` |
| Disputes | `dispute_escalated`, `dispute_resolved` |
| Users | `user_verified` |
| System | `anchor_computed`, `dispute_metrics_recorded`, `dispute_tuning_recommended` |

"Deliberation events" (default view) includes all of the above except System. This covers: `submission_received`, `submission_rejected_not_policy`, `candidate_created`, `cluster_created`, `cluster_updated`, `cluster_merged`, `ballot_question_generated`, `policy_options_generated`, `vote_cast`, `policy_endorsed`, `cycle_opened`, `cycle_closed`, `dispute_escalated`, `dispute_resolved`.

## Constraints

- NO login required. The audit trail is public.
- PII is stripped server-side before serving (`user_id`, `email`, `account_ref`, `wa_id`).
- `raw_text` (civic concerns) is preserved — it's content, not PII.
- Chain verification is server-side via `GET /analytics/evidence/verify`. Client-side `verifyChain()` is retained in lib for offline/advanced use.
- Canonical JSON serialization must match between Python (`json.dumps(sort_keys=True, separators=(",",":"))`) and TypeScript (`canonicalJson()` in `web/lib/evidence.ts`).
- Pagination is required — never load the entire chain at once.

## Tests

Tests in `web/tests/evidence-page.test.tsx` (17 tests) and `web/tests/evidence.test.ts` (15 tests):
- Page renders heading, verify button, filter pills
- Entries load and display human-readable descriptions
- Search filters by description, entity_id, hash
- Expand/collapse works (click + Enter keypress)
- Pagination (Next/Previous, page increment, disabled states)
- Chain verification (valid + invalid server responses)
- Error handling (API failure → empty state)
- Total entries count from API
- `canonicalJson()` parity with Python `json.dumps`
- `verifyChain()` detects tampered hash, prev_hash, metadata
