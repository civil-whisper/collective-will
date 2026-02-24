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

## Decision: Inline canonicalization + embedding at intake

**Why this changed from deferred-only**

- Previously, intake stored the submission with `status="pending"` and all processing happened in the batch scheduler.
- Users had no feedback until the next batch run (up to 6 hours), making the system feel unresponsive.
- Garbage submissions (greetings, spam, off-topic) consumed pipeline resources during batch processing.

**Why inline is correct**

- Immediate feedback: users see the canonical title in their confirmation message, or a contextual rejection reason.
- Garbage rejection at submission time prevents waste of downstream LLM and clustering resources.
- Anti-abuse: rejected garbage still counts against `MAX_SUBMISSIONS_PER_DAY` since the `Submission` record is created before canonicalization.
- Embedding inline (~100ms) makes candidates immediately visible in analytics.

**Locale-aware messaging**

- User-facing messages (confirmation, rejection, errors) are sent in the user's locale (`user.locale`).
- Supported: Farsi (`fa`) and English (`en`), with English as default fallback.
- Rejection reasons from the LLM are in the user's input language (not necessarily the same as `user.locale`, but matching the language they wrote in).

**Risk**

- LLM latency at submission time (~2-5s). Acceptable for messaging apps where typing indicators are common.
- LLM outage degrades to batch mode: user gets generic confirmation without canonical title.

**Guardrail**

- No WhatsApp/Evolution payload assumptions inside intake handler; interact via `BaseChannel` only.
- No raw-content persistence for PII-rejected submissions (log only minimal reason codes).
- Graceful degradation: if inline canonicalization fails, submission stays `status="pending"` and batch scheduler retries.
- All user-facing messages are locale-aware via `_msg(locale, key, **kwargs)` helper.

**Verdict**: **Inline canon + embed with batch fallback**
