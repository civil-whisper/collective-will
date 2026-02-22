# Decision Rationale — messaging/04-submission-intake.md

> **Corresponds to**: [`docs/agent-context/messaging/04-submission-intake.md`](../../agent-context/messaging/04-submission-intake.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Intake is business logic, not transport logic.
- It should depend on `BaseChannel` for responses and `UnifiedMessage` for input, regardless of current provider.
- Submission age eligibility should use config (`MIN_ACCOUNT_AGE_HOURS`, default `48`) so tests can run with lower thresholds.
- Intake should not grant contribution credit by itself; contribution unlock comes from accepted submissions or endorsements.
- Intake should run automated pre-persist PII screening; if high-risk PII is detected, ask the user to redact and resend instead of storing raw text.

**Guardrail**: No WhatsApp/Evolution payload assumptions inside intake handler, and no raw-content persistence for PII-rejected submissions (log only minimal reason codes).
