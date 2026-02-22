# Decision Rationale — website/05-analytics-top-policies.md

> **Corresponds to**: [`docs/agent-context/website/05-analytics-top-policies.md`](../../agent-context/website/05-analytics-top-policies.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements public-results transparency decisions as:

- Ranked top-policy view by approval counts/rates.
- Cycle selector for historical comparison.
- Public visibility with no voter-identity exposure.
- Deterministic tie-handling requirements.

---

## Decision: Public ranked priorities with cycle context

**Why this is correct**

- Makes collective priorities legible to users and observers.
- Connects voting outcomes directly to transparent cluster artifacts.
- Preserves privacy by exposing aggregates only.

**Risk**

- Ranking ambiguity (especially ties) can reduce perceived fairness.

**Guardrail**

- Keep tie ranking deterministic and tested.
- Show cycle metadata (`total_voters`, date range) with results.
- Never expose per-voter records in this surface.

**Verdict**: **Keep with guardrail**
