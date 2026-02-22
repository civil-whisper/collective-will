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
