# Decision Rationale — messaging/07-voting-service.md

> **Corresponds to**: [`docs/agent-context/messaging/07-voting-service.md`](../../agent-context/messaging/07-voting-service.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Voting flow should remain transport-agnostic to avoid provider lock-in.
- Ballot delivery and reminders are sent through `BaseChannel` only.
- Vote age eligibility should use config (`MIN_ACCOUNT_AGE_HOURS`, default `48`) rather than hardcoded literals to support fast test cycles.
- Contribution gate is multi-path: processed submission OR pre-ballot endorsement signature.
- Pre-ballot endorsement stage should be recorded and auditable before final ballot participation.
- Vote-change semantics are explicit: one full approval-set re-submission per cycle (total 2 vote submissions max).

**Guardrail**: Keep vote lifecycle and tallying independent from WhatsApp-specific classes/payloads, enforce one-signature-per-user-per-cluster idempotency in endorsement flow, implement vote-change checks at full vote-set level (not per-cluster toggles), and prohibit manual per-user vote overrides.
