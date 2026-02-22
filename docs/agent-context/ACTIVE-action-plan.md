# Active Action Plan (Current Cycle)

This file is the operational plan for the current remediation cycle.
If this file conflicts with `CONTEXT-shared.md`, update both in the same change.

## Current Channel Policy

- MVP build/testing transport: Telegram (`TelegramChannel`)
- WhatsApp Evolution transport: deferred to post-MVP rollout after anonymous SIM operations are ready
- `BaseChannel` boundary remains mandatory for all handlers/pipeline entry points

## Priority Workstreams

### P0 — Resolve Critical Runtime Gaps

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

## Definition of Done (This Cycle)

- No CI/CD job performs paid LLM API calls
- Dispute lifecycle has automated open->resolved path with evidence trace
- Pipeline/voting contracts match context thresholds and endorsement gates
- Context + decision-rationale docs are synchronized with implemented behavior
