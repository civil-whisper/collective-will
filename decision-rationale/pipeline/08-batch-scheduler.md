# Decision Rationale — pipeline/08-batch-scheduler.md

> **Corresponds to**: [`docs/agent-context/pipeline/08-batch-scheduler.md`](../../agent-context/pipeline/08-batch-scheduler.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext coordinates pipeline execution decisions as:

- 6-hour batch orchestration across canonicalization -> embeddings -> clustering -> variance -> summaries -> agenda.
- Idempotent processing of pending-only submissions.
- Concurrency lock to prevent parallel pipeline runs.
- Step-scoped transactions and resilient partial-failure handling.

---

## Decision: Simple autonomous scheduler over heavy queueing

**Why this is correct**

- Matches v0 scale and keeps operations lightweight.
- Easier to reason about ordering and reproducibility.
- Supports autonomous operation without per-run human intervention.

**Risk**

- Overlapping runs or weak locking can corrupt progress assumptions.
- Silent partial failures can degrade output quality over time.

**Guardrail**

- Enforce single-run lock (advisory/file lock) in scheduler process.
- Emit structured run metrics/errors for each step.
- Keep idempotency tests and partial-failure tests mandatory.

**Verdict**: **Keep with guardrail**
