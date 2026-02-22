# Decision Rationale — messaging/06-abuse-rate-limiting.md

> **Corresponds to**: [`docs/agent-context/messaging/06-abuse-rate-limiting.md`](../../agent-context/messaging/06-abuse-rate-limiting.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This file operationalizes D3 abuse guardrails around identity/signup:

- per-IP signup cap (blocking)
- non-major-domain signup cap
- distinct-domain-per-IP anomaly detection
- disposable-domain trust scoring
- account-creation velocity telemetry
- reachable burst trigger (`3 submissions / 5 minutes`) with soft quarantine handling

---

## Decision: Use layered signup controls in v0 (blocking + telemetry)

**Why this is correct**

- Per-IP caps block obvious burst abuse quickly.
- Non-major-domain caps reduce disposable-domain account farms.
- Major provider exemptions reduce collateral damage for legitimate users.
- Telemetry signals still provide early warning without adding unnecessary friction.

**Risk**

- Shared IP environments can be temporarily constrained if caps are too low.
- Determined Sybil actors can still distribute across IP space and provider mix.

**Guardrail**

- Keep per-IP caps and non-major-domain caps configurable for tuning.
- Keep major-provider exemption list explicit and editable.
- Keep telemetry signals non-blocking and use them for automated triage/`trust_score` policies.
- Keep burst soft-quarantine threshold reachable and configurable; watch false positives and adjust safely per environment.
- Quarantine release/hold decisions are policy-driven and autonomous; humans tune policy but do not adjudicate single accounts.
- Require evidence logging for quarantine adjudication actions (enter/hold/release) so autonomous decisions remain auditable.

**Verdict**: **Keep with guardrail**
