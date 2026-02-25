# Decision Rationale — messaging/07-voting-service.md

> **Corresponds to**: [`docs/agent-context/messaging/07-voting-service.md`](../../agent-context/messaging/07-voting-service.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Voting flow remains transport-agnostic via `BaseChannel`.
- Ballot delivery and reminders sent through `BaseChannel.send_message()` with `reply_markup` inline keyboards.
- Vote age eligibility uses config (`MIN_ACCOUNT_AGE_HOURS`, default `48`).
- Contribution gate is multi-path: processed submission OR pre-ballot endorsement signature.
- Pre-ballot endorsement stage is recorded and auditable before final ballot participation.
- Vote-change semantics: one full vote-set re-submission per cycle (total 2 submissions max).
- Per-policy voting: `cast_vote()` accepts `selections` (list of `{cluster_id, option_id}` dicts) alongside legacy `approved_cluster_ids`.
- Tally produces both `approval_count`/`approval_rate` and per-option `option_counts` when selections are present.

## Decision: Per-policy stance voting over approval voting

**Why this is correct**

- Captures nuanced positions (support, oppose, conditional, alternative approaches) rather than binary approve/reject.
- LLM-generated options surface perspectives users may not have considered.
- `approved_cluster_ids` is auto-derived from `selections` for backward compatibility with existing analytics.

**Risk**

- More complex UX flow (paginated, one-at-a-time) may increase drop-off compared to single-page approval ballot.
- LLM option quality varies — bad options could mislead voters.

**Guardrail**

- Fallback to generic support/oppose options when LLM generation fails — voting is never blocked.
- Skip button allows users to abstain on individual policies.
- Summary review page lets users verify all choices before final submission.
- Keep vote lifecycle and tallying independent from platform-specific classes/payloads.
- Enforce one-signature-per-user-per-cluster idempotency in endorsement flow.
- Implement vote-change checks at full vote-set level (not per-cluster toggles).
- Prohibit manual per-user vote overrides.

**Verdict**: **Keep with guardrail**
