# Active Action Plan (Current Cycle)

This file is the operational plan for the current remediation cycle.
If this file conflicts with `CONTEXT-shared.md`, update both in the same change.

## Current Channel Policy

- MVP build/testing transport: Telegram (`TelegramChannel`)
- WhatsApp Evolution transport: deferred to post-MVP rollout after anonymous SIM operations are ready
- `BaseChannel` boundary remains mandatory for all handlers/pipeline entry points

## Priority Workstreams

### P0 — Staging Debug Sprint (Current)

Design rationale: `docs/decision-rationale/staging-debug-sprint.md`

Goal: enable real-user end-to-end testing on the staging environment with a small
group. Fix persistence gaps and relax guards so the full flow works immediately
after signup.

**Phase 1 — Fix Persistence Showstoppers**

24. [done] Persist Telegram sealed mapping to database
    - Added `sealed_account_mappings` table (platform, platform_id, account_ref)
    - Added Alembic migration `002_staging_persistence`
    - Replaced in-memory dicts in `src/channels/telegram.py` and `src/channels/whatsapp.py`
    - Updated `BaseChannel.parse_webhook` to async
    - Updated webhook handlers to pass db session through to channels

25. [done] Persist magic links and linking codes to database
    - Added `verification_tokens` table (token, email, token_type, expires_at, used)
    - Replaced in-memory dicts in `src/handlers/identity.py` with DB operations via `src/db/verification_tokens.py`

**Phase 2 — Make All Guards Config-Backed**

26. [done] Add missing config fields to `src/config.py`
    - `voting_cycle_hours: int = 48` (env: `VOTING_CYCLE_HOURS`)
    - `max_submissions_per_day: int = 5` (env: `MAX_SUBMISSIONS_PER_DAY`)
    - `require_contribution_for_vote: bool = True` (env: `REQUIRE_CONTRIBUTION_FOR_VOTE`)
    - Wired into voting, abuse, and commands handlers

27. [done] Update staging `.env` with relaxed values
    - `deploy/.env.staging` updated with all relaxed guard overrides

**Phase 3 — Deploy & Wire Up**

28. [done] Add Telegram webhook registration helper script
    - `scripts/register-telegram-webhook.sh`

29. [done] Rotate and remove committed staging secrets
    - Replaced `deploy/.env.staging` with placeholder-only version

30. [done] Write/update tests for persistence changes (256 passed, 22 skipped)
    - Updated all channel tests to mock DB-backed sealed mapping
    - Updated identity tests to mock DB-backed verification tokens
    - Updated all FakeChannel subclasses for async parse_webhook
    - Added test for `require_contribution=False` vote eligibility
    - Updated webhook tests with correct mock paths

### P0 — Resolve Critical Runtime Gaps (Done)

1. [done] Implement autonomous dispute resolution workflow
   - Open dispute -> adjudication run -> confidence check -> fallback/ensemble path -> resolved state
   - Evidence-log every adjudication step
   - Enforce submission-scoped re-canonicalization (no full mid-cycle re-cluster for one dispute)

2. [done] Fix evidence event taxonomy consistency
   - Align emitted event types with `VALID_EVENT_TYPES`
   - Add tests that fail if handlers emit unknown event types

3. [done] Fix messaging transport correctness
   - Keep Telegram outbound path stable for MVP testing
   - For post-MVP WhatsApp adapter work, ensure outbound send reverses opaque `account_ref -> wa_id` through sealed mapping

### P1 — Align Voting/Pipeline Behavior with Contracts

4. [done] Correct cycle assembly and agenda qualification flow
   - Populate cycle cluster IDs correctly
   - Use real endorsement counts in agenda gating
   - Keep `MIN_PREBALLOT_ENDORSEMENTS` and size thresholds config-backed

5. [done] Add dispute metrics and SLA telemetry
   - Track resolution latency, disagreement/escalation rates, dispute volume ratio
   - Trigger policy/model tuning workflow when thresholds are exceeded

### P1 — LLM Cost Control in CI/CD

6. [done] Disable live LLM/API usage in CI/CD
   - CI must not run tests that can call paid LLM providers
   - Keep comprehensive pipeline generation as manual/local-only operation

7. [done] Shift CI verification to cached/fixture-driven pipeline tests
   - Run canonicalization/embedding once (manual cache generation)
   - Store replayable artifacts (fixture/cache) for non-network test runs
   - Validate clustering, agenda, evidence chain, and API behavior using cached outputs

### P2 — Website Redesign (Plausible-Inspired Analytics UI)

Design reference: `docs/decision-rationale/website-design-system.md`
Inspiration: [Plausible Analytics](https://plausible.io/plausible.io) — clean, minimal, single-page analytics dashboard.

**Phase 1 — Foundation (Tailwind + Design Tokens + Fonts)**

8. [done] Install and configure Tailwind CSS v4
   - Add `tailwindcss`, `@tailwindcss/postcss`, and `postcss` as dev dependencies
   - Create `postcss.config.mjs` with Tailwind plugin
   - Replace `globals.css` with Tailwind directives and custom theme tokens (colors, fonts, spacing from design system doc)
   - Configure `tailwind.config.ts` with custom color palette, dark mode (`class` strategy), and RTL plugin
   - Add `Inter` (Latin) and `Vazirmatn` (Farsi) via `next/font/google` in the root layout
   - Verify the build compiles and existing pages still render (no visual regression needed yet — they'll be restyled next)

**Phase 2 — Shared UI Components**

9. [done] Build core reusable components in `web/components/ui/`
   - `Card` — surface container with border, rounded corners, padding, dark mode
   - `MetricCard` — big number + label + optional trend arrow (props: `label`, `value`, `trend?`, `trendDirection?`)
   - `PageShell` — consistent max-width container, page title, subtitle
   - `DomainBadge` — colored pill for policy domain enum
   - `ChainStatusBadge` — green valid / red broken indicator
   - `BreakdownRow` — single row with name, value, percentage bar background
   - `BreakdownTable` — ranked list of `BreakdownRow`s inside a Card, with header
   - Write tests for each component (render, props, a11y)

10. [done] Build `TimeSeriesChart` component
    - Install `recharts` (lightweight, React-native)
    - `TimeSeriesChart` — responsive area chart with configurable data key, fill color from theme
    - Support light/dark mode color switching
    - Support RTL axis label direction
    - Write basic render test

**Phase 3 — Layout & Navigation Redesign**

11. [done] Redesign `NavBar` with Tailwind
    - Sticky top nav with backdrop blur
    - Logo/app name on the start side, links on the end side
    - Mobile: hamburger menu with slide-down drawer
    - Active link indicator (underline or background highlight)
    - Language switcher styled as a clean pill/dropdown
    - Dark mode toggle (optional for v0, but prepare the CSS variable structure)

12. [done] Redesign root layout (`app/[locale]/layout.tsx`)
    - Apply font classes (Inter for `en`, Vazirmatn for `fa`)
    - Set `<html>` dark mode class from cookie or system preference
    - Add consistent page-level padding and max-width via `PageShell`
    - Ensure RTL direction attribute is respected by Tailwind utilities

**Phase 4 — Page Redesigns**

13. [done] Redesign Landing Page (`app/[locale]/page.tsx`)
    - Hero section: headline + subtitle centered, generous vertical padding
    - `SubscribeForm` styled as a single-row input+button with rounded corners
    - "How it works" as a 4-column icon+text grid (responsive to 2-col on tablet, stacked on mobile)
    - "Everything is auditable" trust section with `ChainStatusBadge` preview and link to evidence page
    - Clean footer with minimal links

14. [done] Redesign Analytics Overview Page (`app/[locale]/analytics/page.tsx`)
    - Top row: 3–4 `MetricCard`s (total voters, active clusters, submissions this cycle, current cycle)
    - Center: `TimeSeriesChart` showing participation over recent cycles or days
    - Below chart, two-column layout:
      - Left: `BreakdownTable` for top clusters by approval (clickable, links to cluster detail)
      - Right: `BreakdownTable` for policy domain distribution
    - Bottom: recent evidence activity feed (last 5 entries, link to full evidence page)
    - Time range selector (current cycle / last 7 days / last 30 days / all time)

15. [done] Redesign Top Policies Page (`app/[locale]/analytics/top-policies/page.tsx`)
    - Ranked list using `BreakdownTable` component
    - Each row: rank badge, cluster summary (link), approval rate bar, approval count, domain badge
    - Clean header with page title and cycle selector

16. [done] Redesign Cluster Detail Page (`app/[locale]/analytics/clusters/[id]/page.tsx`)
    - Top: cluster summary as page title, domain badge, summary_en subtitle
    - Metric row: member count, approval count, variance flag indicator
    - Grouping rationale in a subtle callout box
    - Candidates list as styled cards (title, summary, domain badge, confidence bar)

17. [done] Redesign Evidence Page (`app/[locale]/analytics/evidence/page.tsx`)
    - `ChainStatusBadge` prominently at the top with verify button
    - Search input styled with Tailwind (rounded, icon prefix)
    - Evidence entries as collapsible cards (event type + timestamp visible, payload expandable)
    - Pagination styled as pill buttons
    - Hash values in monospace with copy-to-clipboard button

18. [done] Redesign User Dashboard (`app/[locale]/dashboard/page.tsx`)
    - Top row: `MetricCard`s for total submissions, total votes
    - Submissions list as clean cards with status badge, candidate info, cluster link, dispute controls
    - `DisputeButton` and `DisputeStatus` restyled with Tailwind (radio as styled pill selectors, textarea with focus ring)
    - Votes section as simple card list

19. [done] Redesign Auth Pages (sign-in, verify)
    - Centered card layout
    - Clean form inputs with labels, focus states, error messages
    - Consistent with overall design language

**Phase 5 — Polish & QA**

20. [done] Responsive QA pass (Tailwind responsive classes applied throughout)
    - Test all pages at mobile (375px), tablet (768px), desktop (1280px)
    - Fix any layout breaks, overflow issues, or touch target problems

21. [done] RTL QA pass (logical properties ms-/me-/ps-/pe- used throughout)
    - Test all pages in Farsi locale
    - Verify logical properties, chart direction, nav layout, text alignment
    - Fix any bidirectional text issues

22. [done] Accessibility pass (focus-visible, ARIA labels, semantic HTML)
    - All interactive elements have visible focus indicators
    - Color contrast meets WCAG AA (4.5:1 for text)
    - Screen reader testing for metric cards, charts, expandable evidence entries
    - ARIA labels on all icon-only buttons

23. [done] Update tests (all 122 tests pass across 16 files)
    - Update existing component tests for new Tailwind class names
    - Add new tests for new UI components
    - Ensure all tests pass

### P1 — Signup Flow (Two-Step Email + Telegram Linking)

31. [done] Create `/signup` page with two-step guided flow
    - Step 1: Email form → calls `/auth/subscribe` → shows "check your email" confirmation
    - Step 2: After magic link click, `/verify` shows linking code + Telegram bot deep link
    - Visual step indicator (1. Verify Email, 2. Connect Telegram)
    - Info blurbs explain why email/Telegram, no phone numbers collected
    - Rate limit and error states handled
    - Links to sign-in for existing users

32. [done] Redesign `/verify` page for Telegram linking
    - Step indicator showing email completed, Telegram active
    - Linking code display with copy button
    - "Open Telegram Bot" deep link button
    - Code expiry notice (60 minutes)
    - Error states: expired vs invalid tokens, link back to `/signup`

33. [done] Update landing page and navigation
    - Hero CTAs: "Join Now" → `/signup` + "Start the Bot on Telegram" → `t.me/...`
    - NavBar: "Sign Up" button in desktop + mobile nav
    - Removed `SubscribeForm` as primary entry point (component still exists)

34. [done] Full i18n for signup/verify flows
    - Added `signup.*` (14 keys) and `verify.*` (12 keys) namespaces
    - Added `common.signup` and `landing.joinCta` keys
    - Farsi + English parity verified by tests

35. [done] Tests for signup flow (all 139 tests pass across 17 files)
    - New `signup-page.test.tsx` (11 tests)
    - Updated `verify-page.test.tsx` (10 tests)
    - Updated `navbar.test.tsx` (9 tests)
    - Updated `messages.test.ts` (8 tests)

### P0 — Real Email Sending (Resend)

36. [done] Implement email sender module (`src/email/sender.py`)
    - Async Resend API integration via httpx (no new dependencies)
    - Bilingual HTML + plain-text templates (Farsi/English)
    - Console fallback when `RESEND_API_KEY` is unset (preserves dev experience)
    - Email failure does not crash signup flow (logs warning, token still valid)

37. [done] Wire email sending into identity handler
    - Replaced `logging.info` stub with `send_magic_link_email()` call
    - Both new-user and existing-user (re-verify) paths now send email
    - Added `resend_api_key` and `email_from` to `Settings`

38. [done] Tests for email sending (12 new tests + 1 updated)
    - Template content tests (HTML/plain-text, both locales, expiry notice)
    - API call tests (correct payload, auth header)
    - Error handling (API error, network error)
    - Console fallback (no API key, empty API key)
    - Updated identity test to mock email sender

### P1 — Ops Observability Console

Design rationale: `docs/decision-rationale/website/09-ops-debug-console.md`

39. [done] Add `/ops` diagnostics console (dev/staging first)
    - Add feature-flagged `/ops` page and optional nav tab
    - Add backend `/ops/status`, `/ops/events`, and `/ops/jobs` endpoints
    - Keep production mode admin-gated and hidden unless explicitly enabled
    - Expose structured redacted diagnostics, not raw container logs
    - Add i18n + tests for access control, filtering, and redaction
    - Add request correlation IDs (`X-Request-Id`) and include them in ops event traces

40. [done] Unify authenticated web API auth across dashboard and ops
    - Standardized on backend-verified bearer tokens for `/user/*` and `/ops/*`
    - Removed client-trusted email-header identity path for authenticated access control
    - Added shared backend/web auth helpers to keep auth behavior consistent across tabs

### P0 — Auth & Deploy Routing Fixes

41. [done] Fix Caddy reverse-proxy path stripping
    - Changed `handle_path` → `handle` + `uri strip_prefix /api` for backend auth routes
    - `handle_path` was stripping the entire matched prefix (e.g., `/api/auth/subscribe` → `/`),
      so all signup/verify/web-session and NextAuth endpoints returned errors
    - NextAuth routes now pass through with full `/api/auth/*` path (no stripping)
    - Documented Caddy routing pattern in `deploy/README.md`

42. [done] Fix server-side API base resolution
    - `web/lib/api.ts` now checks `BACKEND_API_BASE_URL` on server side (like auth-config already did)
    - Fixes Ops page, dashboard, and all SSR API calls that couldn't reach `http://backend:8000`
    - Fixed disputes route handler to use `resolveServerApiBase()` instead of hardcoded base

43. [done] Make NavBar session-aware
    - Layout passes `userEmail` from server-side `auth()` to NavBar
    - Shows email when logged in, "Sign Up" when not
    - Added test for logged-in vs logged-out navbar state

44. [done] Fix verify page session establishment
    - `signIn()` call is now awaited (was fire-and-forget)
    - On success: sets `loggedIn` state, calls `router.refresh()` to update NavBar
    - Added "Go to Dashboard" button after successful verification

### P0 — Audit Evidence Redesign

Design rationale: Plan in `.cursor/plans/audit_evidence_redesign_2514d858.plan.md`

Goal: Transform the evidence chain from opaque hash dumps into a meaningful,
human-readable audit trail connected to analytics. Fresh start (no backward
compatibility with old sparse payloads).

**Phase 1 — Backend Payload Enrichment**

45. [done] Enrich all `append_evidence` call sites with human-readable payload fields
    - `intake.py`: `submission_received` → raw_text, language, status, submission_id, user_id
    - `identity.py`: `user_verified` → user_id, method (removed account_ref PII)
    - `voting.py`: `vote_cast` → user_id, cycle_id; `cycle_opened` → cycle_duration_hours
    - `canonicalize.py`: `candidate_created` → submission_id, summary, stance
    - `summarize.py`: `cluster_updated` → summary_en, domain, member_count, candidate_ids
    - `disputes.py`: `dispute_resolved` → resolved_title, resolved_summary

46. [done] Remove `dispute_opened` emission + clean up VALID_EVENT_TYPES
    - Removed `dispute_opened` and `user_created` from `VALID_EVENT_TYPES`
    - Removed `dispute_opened` evidence append from `src/api/routes/user.py`
    - Updated `_record_dispute_metrics` to count `dispute_resolved` instead of `dispute_opened`

**Phase 2 — API Improvements**

47. [done] Add PII stripping to `GET /analytics/evidence`
    - `strip_evidence_pii()` removes `user_id`, `email`, `account_ref`, `wa_id` from payloads
    - Added pagination (`page`, `per_page`), `entity_id` and `event_type` query filters
    - Response format: `{total, page, per_page, entries}`

48. [done] Add server-side `GET /analytics/evidence/verify`
    - Calls `db_verify_chain()` server-side; returns `{valid, entries_checked}`
    - Replaced old POST client-verify endpoint

**Phase 3 — Frontend Redesign**

49. [done] Build `eventDescription()` mapper + i18n keys (en + fa)
    - Maps all 14 event types to human-readable strings with template variables
    - Added `analytics.events.*` keys in both `en.json` and `fa.json`
    - Added filter category labels and UI text

50. [done] Redesign evidence page with human-readable cards
    - Category filter pills (Submissions, Policies, Votes, Disputes, Users, System)
    - Smart default: deliberation events only, toggle to show all
    - Collapsible entry cards with description, key-value fields, full payload, hash chain
    - Entity filtering via `?entity=UUID` query param
    - Deep links from entries to analytics pages

**Phase 4 — Cross-Linking**

51. [done] Add 'View Audit Trail' links on analytics pages
    - Cluster detail page: audit trail link card
    - Top policies page: audit trail icon per policy row

**Tests & Docs**

52. [done] Update all tests (154 frontend + 309 backend passing)
    - Updated 7 backend test files for new payloads, event types, API format
    - Rewrote evidence-page.test.tsx (17 tests) for redesigned page
    - Updated setup.ts `makeTranslator` for nested keys + template substitution

53. [done] Document volume nuke reset in deploy README

### P0 — Inline Canonicalization & Garbage Rejection

Design rationale: `docs/decision-rationale/pipeline/08-batch-scheduler.md`, `docs/decision-rationale/pipeline/03-canonicalization.md`

Goal: Move canonicalization and embedding from batch-only to inline at submission
time. Detect and reject garbage submissions immediately. Provide locale-aware
feedback to users.

54. [done] Implement inline canonicalization in intake handler
    - `canonicalize_single()` runs at submission time in `src/handlers/intake.py`
    - Returns `PolicyCandidateCreate` (valid) or `CanonicalizationRejection` (garbage)
    - Inline embedding via `compute_and_store_embeddings()` after canonicalization
    - Graceful fallback: LLM failure → `status="pending"` → batch scheduler retries

55. [done] Add garbage rejection with contextual feedback
    - LLM prompt evaluates `is_valid_policy` and provides `rejection_reason` in input language
    - Rejected submissions get `status="rejected"` and evidence event `submission_rejected_not_policy`
    - Rejected submissions still count against `MAX_SUBMISSIONS_PER_DAY` (anti-sybil)

56. [done] Add locale-aware user messaging
    - Replaced hardcoded Farsi messages with `_MESSAGES` dict (Farsi + English)
    - `_msg(locale, key, **kwargs)` helper selects language based on `user.locale`
    - Confirmation includes canonical title; rejection includes contextual reason

57. [done] Enforce English-only canonical output
    - Updated LLM prompt: `title`, `summary`, `entities` always in English
    - `rejection_reason` in the same language as the input
    - Batch scheduler updated to handle `status="canonicalized"` and `status="pending"` (fallback)

58. [done] Update analytics unclustered candidates display
    - `/analytics/unclustered` endpoint now includes `raw_text` and `language` from Submission
    - Frontend shows original user message, AI interpretation (canonical title/summary), and AI confidence %
    - RTL-aware display for Farsi submissions

59. [done] Update tests for inline processing
    - `test_intake.py`: tests for garbage rejection, LLM failure fallback, locale-aware messages
    - `test_canonicalize.py`: tests for `canonicalize_single` (valid + garbage), batch filtering
    - Added `submission_rejected_not_policy` to `VALID_EVENT_TYPES`

## Definition of Done (This Cycle)

- No CI/CD job performs paid LLM API calls
- Dispute lifecycle has automated open->resolved path with evidence trace
- Pipeline/voting contracts match context thresholds and endorsement gates
- Context + decision-rationale docs are synchronized with implemented behavior

### Website Redesign Definition of Done

- Tailwind CSS configured with custom theme, dark mode, RTL support
- All pages restyled in Plausible-inspired design (no inline styles remaining)
- Shared UI components built and tested (`MetricCard`, `BreakdownTable`, `TimeSeriesChart`, etc.)
- Time-series chart renders on analytics overview
- Responsive at mobile/tablet/desktop breakpoints
- RTL (Farsi) layout verified with no visual regressions
- All existing + new tests pass
- No accessibility regressions (focus states, contrast, ARIA labels)
