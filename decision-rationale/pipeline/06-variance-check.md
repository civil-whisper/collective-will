# Decision Rationale — pipeline/06-variance-check.md

> **Corresponds to**: [`docs/agent-context/pipeline/06-variance-check.md`](../../agent-context/pipeline/06-variance-check.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext supports clustering transparency decisions as:

- Multi-run clustering variance checks (default 3 runs).
- Jaccard-overlap stability scoring.
- `variance_flag` as informational transparency signal, not suppression.

---

## Decision: Flag unstable clusters instead of hiding them

**Why this is correct**

- Makes clustering uncertainty visible to users.
- Preserves transparency while avoiding overconfidence in one run.
- Keeps v0 simple: compare alternates, persist primary run only.

**Risk**

- Extra runs increase compute cost.
- Low-volume or borderline datasets can over-flag instability.

**Guardrail**

- Keep variance-check optional for tiny batches.
- Persist only primary run and treat alternates as transient comparisons.
- Keep instability threshold configurable and test call-count/order behavior.

**Verdict**: **Keep with guardrail**
