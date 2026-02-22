# Decision Rationale — pipeline/03-canonicalization.md

> **Corresponds to**: [`docs/agent-context/pipeline/03-canonicalization.md`](../../agent-context/pipeline/03-canonicalization.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- D8 is now Sonnet-first for canonicalization.
- Goal is extraction quality and operational simplicity, not lowest per-call cost.

## Decision: Use single-model Sonnet for canonicalization

**Why this is correct**

- Better handling of nuanced Farsi political text, reducing downstream clustering errors.
- Simpler operations than multi-model adjudication/routing in v0.
- Cleaner audit trail: one primary model for canonicalization outputs.

**Risk**

- Model outage can block pipeline if no fallback exists.
- High-quality models can still produce schema-invalid JSON intermittently.

**Guardrail**

1. Strict JSON schema validation before saving candidates.
2. Automatic review path for low-confidence outputs.
3. Haiku fallback only for continuity, with fallback results explicitly flagged.

**Verdict**: **Keep with guardrail**
