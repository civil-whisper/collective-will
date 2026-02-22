# Decision Rationale — website/06-dashboard-submissions-votes.md

> **Corresponds to**: [`docs/agent-context/website/06-dashboard-submissions-votes.md`](../../agent-context/website/06-dashboard-submissions-votes.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements user-sovereignty and privacy decisions as:

- Authenticated users can inspect their own submissions and vote history.
- Original raw submission text is visible only to the submitting user.
- “My vote counted” links to evidence artifacts (not cosmetic status).
- Dashboard remains private while analytics stay public.

---

## Decision: Personal transparency dashboard with strict ownership boundaries

**Why this is correct**

- Gives users verifiable visibility into how the system handled their input.
- Supports dispute flow with concrete per-submission context.
- Reinforces trust via evidence-backed vote confirmation.

**Risk**

- Authorization bugs could leak private submission/vote data.

**Guardrail**

- Enforce ownership checks server-side for all dashboard APIs.
- Keep evidence references explicit and auditable.
- Keep raw-text visibility restricted to owner context only.

**Verdict**: **Keep with guardrail**
