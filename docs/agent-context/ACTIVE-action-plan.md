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
   - `TopicBadge` — colored pill for policy_topic (hash-based color)
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
      - Right: `BreakdownTable` for policy topic distribution
    - Bottom: recent evidence activity feed (last 5 entries, link to full evidence page)
    - Time range selector (current cycle / last 7 days / last 30 days / all time)

15. [done] Redesign Community Votes Page (`app/[locale]/collective-concerns/community-votes/page.tsx`)
    - Ranked list using `BreakdownTable` component
    - Each row: rank badge, cluster summary (link), approval rate bar, approval count, topic badge
    - Clean header with page title and cycle selector

16. [done] Redesign Cluster Detail Page (`app/[locale]/analytics/clusters/[id]/page.tsx`)
    - Top: cluster summary as page title, topic badge
    - Metric row: member count, approval count, policy topic
    - Candidates list as styled cards (title, summary, topic badge, confidence bar)

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
    - `summarize.py`: `cluster_updated` → summary, member_count, candidate_ids
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

### P0 — Telegram UX Redesign & Per-Policy Voting

Goal: Evolve the Telegram bot from ambiguous text commands to a button-only inline
keyboard UX, and upgrade the voting model from approval voting to per-policy stance
voting with LLM-generated options.

**Phase 1 — Button-Only Telegram UX**

60. [done] Replace text commands with inline keyboard buttons
    - Removed all typed command detection (`/start`, `status`, `help`, `vote`, etc.)
    - Main menu rendered as inline keyboard (Submit, Vote, Language toggle)
    - State machine tracks `user.bot_state` for multi-step flows
    - Cancel callback clears state and returns to menu
    - After every action, auto-return to main menu

61. [done] Add callback query support to BaseChannel
    - Extended `UnifiedMessage` with `callback_data` and `callback_query_id`
    - Extended `OutboundMessage` with `reply_markup`
    - Added `answer_callback()` and `edit_message_markup()` to `BaseChannel` (concrete defaults)
    - Implemented in `TelegramChannel`

62. [done] Add analytics deep links
    - After submission: link to public analytics page
    - After voting: link to public analytics with cycle ID

**Phase 2 — Per-Policy Voting with LLM-Generated Options**

63. [done] Create PolicyOption model and migration
    - `policy_options` table (cluster_id, position, label, label_en, description, description_en, model_version)
    - Added `bot_state_data` (JSONB) to `users` table
    - Added `selections` (JSONB) to `votes` table
    - Alembic migrations `004_add_user_bot_state` and `005_per_policy_voting`

64. [done] Implement LLM option generation pipeline (`src/pipeline/options.py`)
    - System prompt for nonpartisan multi-angle option generation
    - 2–4 bilingual stance options per cluster
    - Fallback to generic support/oppose on LLM failure
    - Evidence logging (`policy_options_generated` event)
    - Integrated into scheduler after `summarize_clusters()`

65. [done] Implement paginated per-policy voting UX
    - One policy at a time with inline keyboard options
    - Skip, Back, Change navigation
    - Summary review page before final submission
    - `bot_state_data` persists voting session (cycle_id, cluster_ids, current_idx, selections)

66. [done] Update voting backend for per-policy selections
    - `cast_vote()` accepts `selections` parameter, auto-derives `approved_cluster_ids`
    - `close_and_tally()` produces `option_counts` alongside approval rates
    - Evidence payloads include `selections` data

67. [done] Comprehensive tests (60 handler/pipeline tests, 321 total passing)
    - 23 command handler tests covering all callback paths + edge cases
    - 17 voting handler tests (including selections and option_counts)
    - 13 pipeline options tests (parse, fallback, generation, schema)

68. [done] Web-grounded policy option generation
    - Added `option_generation` LLM tier (Gemini 3.1 Pro primary, Claude Sonnet fallback)
    - Added `grounding: bool` parameter to `LLMRouter.complete()` — enables Google Search grounding for Gemini provider, auto-disabled for non-Google fallback
    - Removed 200-char summary truncation and 15-candidate cap — full submissions passed to LLM
    - Updated system prompt to instruct LLM to search for real-world policy precedents
    - Added 5 new tests (3 LLM grounding + 2 submissions block coverage)

69. [done] Gemini-first model strategy + broadened canonicalization validity
    - Switched all primary LLM tiers to `gemini-3.1-pro-preview` (better performance, lower cost)
    - All fallbacks set to `claude-sonnet-4-20250514` for cross-provider resilience
    - Embeddings switched to `gemini-embedding-001` primary, `text-embedding-3-large` fallback
    - Removed DeepSeek from dispute ensemble (not yet available)
    - Updated `config.py` defaults and `deploy/public.env.staging` to match
    - Broadened canonicalization validity: now accepts questions, concerns, and expressions of interest about policy topics (not just explicit positions/demands)
    - Rationale: questions and stances cluster together by topic; the option generator creates votable stances from the cluster

70. [done] Claude-first model strategy — swap primary/fallback
    - Gemini 3.1 Pro hit 25 RPD (requests/day) limit on Paid Tier 1, causing persistent 429 errors and slow fallback-to-Claude during tests and pipeline runs
    - Switched all primary tiers from `gemini-3.1-pro-preview` to `claude-sonnet-4-6` (released 2026-02-17, same pricing as Sonnet 4)
    - All fallbacks switched from `claude-sonnet-4-20250514` to `gemini-3.1-pro-preview`
    - Ensemble models updated to `claude-sonnet-4-6,gemini-3.1-pro-preview`
    - Embeddings unchanged (Gemini embedding quotas are generous: 3K RPM, unlimited RPD)
    - Google Search grounding for `option_generation` now only activates on Gemini fallback path; override via env if grounding is critical
    - Updated config.py, staging/production deploy envs, .env.example, smoke test, all context docs, and decision rationale

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

### P0 — Clustering Bug Fix & Ops Debug Enhancement

70. [done] Fix numpy ambiguous truth value bug in clustering
    - `cluster.py:71` used `candidate.embedding or []` which raises when embedding is a numpy array (pgvector returns numpy arrays)
    - Removed `or []` fallback — all candidates in the loop already passed the `is not None` filter
    - Existing `test_numpy_array_embeddings_do_not_raise` test now passes in production path

71. [done] Enhance ops console for production debugging
    - `OpsEventHandler` now captures `exc_info` stack traces and exception types into event payloads
    - Scheduler emits structured `scheduler.pipeline.error` and `scheduler.pipeline.completed` events with pipeline context
    - Heartbeat `detail` column widened from `VARCHAR(256)` to `Text` (migration `006_heartbeat_detail_text`)
    - Frontend `OpsEventFeed` now shows expandable payload detail (key-value pairs + formatted tracebacks)
    - Error events auto-expand to show stack trace immediately
    - Added "Scheduler / Pipeline" quick filter for event type filtering
    - Added test for traceback capture in `OpsEventHandler`

### P0 — Policy-Level Clustering Redesign

Design rationale: LLM-driven policy-key grouping is the sole clustering mechanism (HDBSCAN removed).
Two-level structure: `policy_topic` (browsing umbrella) + `policy_key` (ballot-level discussion).
Both are stance-neutral. Three-stage pipeline: inline assignment → hybrid normalization (embedding + LLM) → ballot question generation.

72. [done] Add `policy_topic` + `policy_key` to PolicyCandidate and Cluster models
    - PolicyCandidate: `policy_topic`, `policy_key` columns (indexed, server_default="unassigned")
    - Cluster: `policy_topic`, `policy_key` (unique), `ballot_question`, `ballot_question_fa`,
      `needs_resummarize`, `last_summarized_count`; `cycle_id`, `run_id`, `random_seed` now nullable
    - Alembic migration `007_policy_key_clustering`

73. [done] Update canonicalization for topic-aware policy key assignment (Phase 1)
    - `load_existing_policy_context()` loads existing topics/keys from DB for LLM context
    - LLM prompt updated: produces `policy_topic` and `policy_key` alongside existing canonical fields
    - `_sanitize_policy_slug()` normalizes keys to lowercase-with-hyphens
    - Both `canonicalize_single()` and `canonicalize_batch()` auto-load context if not provided

74. [done] Implement group_by_policy_key() and persistent cluster creation
    - `group_by_policy_key()` in `cluster.py` is the sole grouping mechanism
    - `compute_centroid()` helper for embedding centroids
    - Scheduler `_find_or_create_cluster()` creates or updates persistent clusters
    - Growth detection triggers `needs_resummarize` when membership grows 50%+

75. [done] Implement hybrid embedding + LLM key normalization (Phase 2)
    - `src/pipeline/normalize.py`: `normalize_policy_keys()` uses embedding cosine similarity
      (agglomerative clustering, threshold 0.55) to create broad clusters across ALL topics,
      then sends ALL full summaries to LLM which produces a `key_mapping` (old→canonical).
      LLM may keep, merge, or create new key names.
    - `execute_key_merge()` reassigns candidates, merges cluster IDs, deletes merged clusters
    - All merges evidence-logged as `cluster_merged`
    - Dependencies: numpy, scipy (pdist, linkage, fcluster)

76. [done] Implement ballot question generation (Phase 3)
    - `src/pipeline/endorsement.py`: `generate_ballot_questions()` for clusters needing summarization
    - Generates stance-neutral bilingual ballot questions from member submissions
    - Evidence-logged as `ballot_question_generated`

77. [done] Update scheduler pipeline flow
    - New flow: canonicalize → embed → group by key → normalize keys → ballot questions → options → agenda
    - Removed `create_voting_cycle` call (clusters are persistent, not per-cycle)
    - Agenda gate: `total_support = member_count + endorsements >= min_support`

78. [done] Update agenda to combined support gate
    - Single `min_support` parameter replaces dual `min_cluster_size` + `min_preballot_endorsements`
    - Submissions count as implicit endorsements

79. [done] Tests for all phases (152 passed, 10 skipped)
    - `test_policy_grouping.py`: slug sanitization, grouping, centroid computation
    - `test_normalize.py`: merge response parsing, submissions block building, embedding clustering
    - `test_endorsement.py`: ballot response parsing
    - `test_agenda.py`: combined support gate
    - Updated `test_cluster_agenda.py`, `test_db/test_models.py`, `test_handlers/test_intake.py`
    - HDBSCAN code and tests have been removed

80. [done] Update pipeline documentation and context files
    - Updated CONTEXT-shared.md: Clustering decision, model definitions, directory structure
    - Created `docs/agent-context/pipeline/05-policy-key-grouping.md`
    - Updated ACTIVE-action-plan.md

81. [done] Add LLM grouping integration test
    - `tests/test_pipeline/test_grouping_integration.py`: 100 submissions across 5 policy topics + outliers
    - Serial canonicalization with cumulative policy context (simulates real submission flow)
    - Interleaved hybrid normalization (embedding similarity + LLM confirmation) every 25 submissions
    - `CachingLLMRouter` caches both completions and embeddings to `grouping_cache.json.gz`
    - Generate mode (`GENERATE_GROUPING_CACHE=1`) calls real LLM; replay mode loads from cache (3s)
    - Fuzzy assertions: group cohesion 35%+, separation, outlier isolation, topic consistency
    - Results: hijab 100%, language 100%, internet 100%, privatization 100%, death-penalty 94%
    - Excluded from CI (`scripts/ci-backend.sh`); run manually to validate grouping quality

### P1 — Scheduler Lifecycle Fixes

82. [done] Auto-close expired voting cycles
    - Scheduler `run_pipeline()` now queries for `VotingCycle` with `status="active"` and `ends_at <= now()` at the start of each run
    - Calls `close_and_tally()` for each expired cycle (tallies votes, sets `status="tallied"`, logs `cycle_closed` evidence)
    - Runs before submission processing so the command router stops showing expired cycles immediately
    - Test: `test_expired_cycle_auto_closed` verifies `close_and_tally` is called for expired cycles

83. [done] Fix contribution_count increment
    - Inline path (`intake.py`): `user.contribution_count += 1` after `status="canonicalized"` — users who submit accepted concerns now qualify to vote
    - Batch path (`scheduler/main.py`): eagerly loads `Submission.user`, increments `contribution_count` for each pending sub that produced a candidate
    - Endorsement path (`voting.py`): changed `if count == 0: count = 1` to `+= 1` — each endorsement now adds +1
    - Tests: intake verifies count on success/rejection/LLM-failure; voting verifies 3 sequential endorsements → count==3; scheduler verifies batch increment
    - Context docs updated: `04-submission-intake.md`, `07-voting-service.md`, `08-batch-scheduler.md`, `architecture-flow.md`

84. [done] Hybrid scheduler trigger
    - Added `BATCH_THRESHOLD` (default 10) and `BATCH_POLL_SECONDS` (default 60) config settings
    - Scheduler polls every 60s between runs; triggers immediately when unprocessed count >= threshold
    - Falls back to max interval (`PIPELINE_INTERVAL_HOURS`) if threshold never reached
    - Tests: `test_count_unprocessed`, `test_scheduler_loop_threshold_trigger`, `test_scheduler_loop_time_trigger`

85. [done] Remove summary truncation from LLM prompt builders
    - `normalize.py`: removed 3-summary-per-key cap and 200-char truncation — all candidate summaries included in full
    - `canonicalize.py`: removed 120-char truncation on existing cluster summaries in policy context block
    - `options.py`: removed `[:150]` / `[:100]` truncation in fallback option descriptions
    - `test_grouping_integration.py`: mirrored removals in test helper copies
    - `summarize.py`: confirmed dead code (not called anywhere in src/); left as-is
    - No prompt token limit exists in the LLM router; truncation was unjustified defensive boilerplate

86. [done] Wire Telegram endorse button (pre-ballot endorsement flow)
    - Added "Endorse policies" button to main menu in both locales
    - Paginated one-at-a-time flow: shows ballot question, member count, endorsement count per cluster
    - Pre-ballot only: clusters with `ballot_question IS NOT NULL` excluding those in active voting cycles
    - Tracks already-endorsed clusters in session (hides Endorse button, shows label)
    - Navigation: Endorse (`e:{N}`), Skip (`esk`), Back (`ebk`), Cancel
    - Rewrote `_handle_endorse` to use `bot_state_data` session instead of active voting cycle
    - Rewrote `_build_endorsement_keyboard` for per-cluster display (was all-in-one-row, never called)
    - Added `get_user_endorsed_cluster_ids` query to `db/queries.py`
    - 8 new tests: menu with/without clusters, endorse from session, skip, back, no-session fallback, done state, active-cycle exclusion
    - Context docs updated: `08-message-commands.md`, `architecture-flow.md`

### P1 — Audit Ledger Quality Pass

87. [done] Reverse evidence ledger order to newest-first
    - `GET /analytics/evidence` now orders by `id DESC` (was `ASC`)
    - Page 1 = newest events, higher pages = older
    - Test: `test_returns_newest_first_order`

88. [done] Emit missing cluster_created and cluster_updated evidence events
    - `_find_or_create_cluster()` in `scheduler/main.py` now emits:
      - `cluster_created` when a new cluster is created
      - `cluster_updated` when an existing cluster gains members (skipped if no change)
    - Tests: `test_find_or_create_cluster_emits_cluster_created`, `_updated`, `_skips_event_when_no_change`

90. [done] Stable submission permalinks and full cards in clusters
    - Cluster detail API now includes `raw_text` and `language` via `selectinload(PolicyCandidate.submission)`
    - Cluster detail page shows full candidate cards matching unclustered format (user submission blockquote + AI interpretation)
    - Each candidate card has `id="candidate-{uuid}"` anchor for deep linking with CSS `target:` highlight
    - New API endpoint: `GET /analytics/candidate/{id}/location` returns unclustered/clustered status
    - New `/submission/{id}` Next.js page: resolves candidate location and redirects to the right page with hash anchor
    - Telegram confirmation link updated from `collective-concerns#candidate-{id}` to `submission/{id}`
    - Context doc `04-analytics-cluster-explorer.md` updated to reflect `raw_text` in cluster candidates and new API

89. [done] Complete frontend evidence event coverage
    - Added `submission_rejected_not_policy`, `cluster_merged`, `ballot_question_generated`, `policy_options_generated` to filter categories
    - Split `cluster_created` and `cluster_updated` into separate eventDescription cases
    - Added all missing event descriptions and i18n keys (en + fa)
    - Extended payloadDisplayKeys for new fields (policy_key, growth, survivor/merged keys, option_count)

### P0 — Auto-open Voting Cycles

91. [done] Auto-open voting cycles when qualified clusters are ready
    - `_maybe_open_cycle()` in `scheduler/main.py`: checks for no active cycle, cooldown elapsed, and vote-ready clusters (ballot question + options + endorsement threshold)
    - Called in both early-return (no submissions) and full pipeline paths
    - New config: `auto_cycle_cooldown_hours` (default 1.0, staging 0, production 1)
    - Staging `MIN_PREBALLOT_ENDORSEMENTS` raised from 1 to 5; `VOTING_CYCLE_HOURS` set to 48 (matching production)
    - `PipelineResult.opened_cycle_id` tracks auto-opened cycles
    - Cluster `status` field (`open`/`archived`) replaces `_clusters_in_completed_cycles()` exclusion
    - Tests: 7 tests covering open, active-cycle skip, cooldown, below-threshold, no-ballot, no-options, no-open-clusters scenarios

92. [done] Voting cycle timing visibility
    - Telegram: `cycle_timing` i18n message shown before ballot with policy count and remaining time
    - Website: green banner on Collective Concerns page when active cycle exists
    - API: `GET /analytics/stats` now returns `active_cycle` object with `id`, `started_at`, `ends_at`, `cluster_count`
    - `_format_cycle_end()` helper produces human-readable remaining time (en/fa)
    - Tests: updated vote callback test, new analytics banner test (web)

94. [done] Cluster lifecycle with open/archived status
    - Added `status` column to `Cluster` model (`open` or `archived`, default `open`)
    - Alembic migration `002_cluster_status`: adds column, status index, replaces unique index on `policy_key` with partial unique index (`WHERE status = 'open'`)
    - `open_cycle()` sets included clusters to `archived` before creating the voting cycle
    - `_find_or_create_cluster()` only matches clusters with `status='open'`; archived policy_keys get fresh open clusters
    - `run_pipeline` and `_maybe_open_cycle` filter by `status='open'` (removed `_clusters_in_completed_cycles`)
    - Analytics API returns `status` on cluster list/detail endpoints; website shows "Archived" badge
    - Updated `ClusterCreate`/`ClusterRead` schemas with `status` field
    - Tests: all 414 backend + 146 web tests pass; new test for archived badge

95. [done] Community Priorities page UX improvements
    - Page title changed from "Clusters" to "Community Priorities" with explanatory description
    - Replaced technical "cluster" terminology with user-friendly alternatives: "Grouped Concerns", "Active Concerns", "Archived Concerns", "Ungrouped Submissions"
    - Open and archived concerns split into separate sections; archived section appears at bottom with description
    - `execute_key_merge()` in `normalize.py` now filters by `status='open'` — archived clusters excluded from merges
    - Endorsement menu in `commands.py` now filters by `status='open'` — archived clusters excluded from endorsement flow
    - Full i18n parity (en + fa)

96. [done] Rename Top Policies to Community Votes
    - Route renamed from `/collective-concerns/top-policies` to `/collective-concerns/community-votes`
    - Nav tab label: "Community Votes" / "آرای جامعه"
    - Page now shows active voting cycle banner + archived voting results
    - Added page description and new empty state messaging
    - All references updated: NavBar, evidence links, Telegram handler, tests, context docs

97. [done] Community Votes: active ballot + archived results with option breakdowns
    - New `GET /analytics/active-ballot` endpoint returns active cycle clusters with ballot questions and options (no per-option counts)
    - `close_and_tally` now snapshots `ballot_question`, `ballot_question_fa`, and `options` (with labels + vote_count) into `cycle.results`, replacing raw `option_counts`
    - Community Votes page redesigned with two sections:
      - Active Ballot: ballot questions, options with descriptions, total voters, time remaining, "results revealed after close"
      - Past Voting Results: ranked list with per-option horizontal vote breakdown bars (vote_count / total, percentage)
    - Full i18n parity (en + fa) for new keys
    - Tests: 416 backend + all web tests pass

93. [done] Prompt cycle close/open in scheduler polling loop
    - Extracted `_close_expired_cycles()` from `run_pipeline` into standalone function
    - Both `_close_expired_cycles()` and `_maybe_open_cycle()` now run every 60s in `scheduler_loop` polling, not just inside `run_pipeline`
    - Prevents cycles staying open past `ends_at` when no submissions trigger the full pipeline (production could delay up to 6h otherwise)
    - Tests: new `test_close_expired_cycles_standalone`, updated scheduler_loop tests

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
