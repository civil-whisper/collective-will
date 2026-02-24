# Decision Rationale — pipeline/08-batch-scheduler.md

> **Corresponds to**: [`docs/agent-context/pipeline/08-batch-scheduler.md`](../../agent-context/pipeline/08-batch-scheduler.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext coordinates pipeline execution decisions as:

- **Inline at submission**: canonicalization + embedding run immediately when a user submits via messaging channel. Garbage is rejected with contextual LLM feedback. Garbage counts against daily quota to prevent sybil LLM-drain attacks.
- **Batch scheduler**: clustering -> variance -> summaries -> agenda run on a config-backed interval.
- **Fallback**: if inline canonicalization fails (LLM outage), submission stays `status="pending"` and the batch scheduler retries.
- Concurrency lock to prevent parallel pipeline runs.

---

## Decision: Inline canonicalization + batch clustering

**Why this changed from full-batch**

- Inline canon gives immediate user feedback (what was understood, or why rejected).
- Garbage rejection at submission time saves pipeline resources and gives users a chance to resubmit.
- Embedding is fast (~100ms) and benefits from running inline so candidates are immediately visible in analytics.
- Clustering inherently needs multiple candidates, so batch scheduling remains correct for that stage.

**Why this is correct**

- Matches v0 scale and keeps operations lightweight.
- Preserves batch-fallback path for resilience during LLM outages.
- Anti-abuse: rejected garbage still counts against `MAX_SUBMISSIONS_PER_DAY` (rate limit query counts all submissions regardless of status).

**Risk**

- LLM latency at submission time (~2-5s). Acceptable for messaging apps.
- LLM outage degrades to batch mode (user gets generic confirmation, not rejection).
- Overlapping scheduler runs or weak locking can corrupt progress assumptions.

**Guardrail**

- Enforce single-run lock in scheduler process.
- Graceful fallback: inline failure -> status="pending" -> batch retries.
- Emit structured run metrics/errors for each step.
- Keep idempotency tests and partial-failure tests mandatory.

**Verdict**: **Inline canon + batch clustering with fallback**
