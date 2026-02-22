# Decision Rationale — website/02-landing-subscribe.md

> **Corresponds to**: [`docs/agent-context/website/02-landing-subscribe.md`](../../agent-context/website/02-landing-subscribe.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements onboarding/trust-loop decisions as:

- Clear mission-first landing content.
- Subscribe form that starts verification flow (not direct account creation).
- Backend-owned subscribe endpoint for anti-abuse and identity logic.
- Prominent transparency/audit cues.

---

## Decision: Low-friction subscribe, backend as source of truth

**Why this is correct**

- Keeps signup simple while preserving abuse controls server-side.
- Aligns with magic-link identity model and no-password policy.
- Communicates transparency early to build user trust.

**Risk**

- Frontend-only validation can still pass malformed or abusive patterns without backend checks.

**Guardrail**

- Keep backend endpoint authoritative for acceptance/rejection.
- Keep success/error copy explicit to avoid false expectations.
- Maintain SSR-first rendering and accessibility for core CTA flow.

**Verdict**: **Keep with guardrail**
