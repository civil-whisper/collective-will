# Decision Rationale — pipeline/04-embeddings.md

> **Corresponds to**: [`docs/agent-context/pipeline/04-embeddings.md`](../../agent-context/pipeline/04-embeddings.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- v0 embeddings are quality-first to maximize clustering effectiveness.
- Embedding selection remains abstraction-driven so later versions can switch to cheaper models without touching pipeline logic.

## Decision: Use strongest embedding model in v0, optimize cost later

**Why this is correct**

- Better embedding quality directly improves cluster cohesion and policy grouping accuracy.
- Keeps implementation simple: one primary embedding model in v0.
- Preserves migration flexibility via `EMBEDDING_MODEL` and `EMBEDDING_FALLBACK_MODEL`.

**Risk**

- Higher per-call cost in v0.
- Provider dependency risk if fallback path is not tested.

**Guardrail**

1. Keep embedding model IDs config-backed.
2. Implement/test fallback embedding model path.
3. Track clustering quality metrics before moving to cost-optimized models.

**Verdict**: **Keep with guardrail**
