# Decision Rationale — website/10-receipt-verification.md

> **Corresponds to**: [`docs/agent-context/website/10-receipt-verification.md`](../../agent-context/website/10-receipt-verification.md)
>
> When a decision changes in either file, update the other.

---

## Decision

Build receipt verification as a **human-readable trust flow** layered on top of the cryptographic audit system.

---

## Why this is correct

- Most users will not verify hashes manually.
- If verification only works for programmers, trust remains socially centralized.
- Clear status states (`Recorded`, `Published`, `Timestamped`) make the system legible without hiding raw proof data from advanced users.

---

## Guardrails

- Keep downloadable proof artifacts available.
- Separate explanatory UX from the independent verification path.
- Link the receipt detail view to the public independent verification guide instead of embedding a long technical checklist inline.
- Avoid overclaiming: status UI must not imply completeness or fairness guarantees beyond anti-tampering after publication.
- Freeze the status vocabulary to five states only (`recorded`, `published`, `timestamped`, `verified`, `failed`) so backend and frontend do not drift.
- Keep “what this proves / does not prove” language stable across FAQ, dashboard, and public audit pages.

---

## Verdict

**Adopt**: verification UX must be understandable by ordinary users, with advanced proof details available but not required.
