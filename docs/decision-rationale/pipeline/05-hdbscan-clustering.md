# Decision Rationale — pipeline/05-policy-key-grouping.md

> **Corresponds to**: [`docs/agent-context/pipeline/05-policy-key-grouping.md`](../../agent-context/pipeline/05-policy-key-grouping.md)
>
> When a decision changes in either file, update the other.

> **Note (superseded):** The original v0 design proposed HDBSCAN clustering. The implementation evolved to LLM-assigned `policy_key` grouping with hybrid normalization (embedding cosine similarity + LLM merge). The rationale below is retained for historical context; the current approach is documented in the agent-context contract.

---

## Decision Alignment

- Clustering uses LLM-assigned `policy_key` grouping with hybrid normalization.
- Apply cold-start guardrail via config-backed `min_cluster_size` per cycle.
- Keep unclustered/noise candidates visible in analytics rather than suppressing them.

## Decision: Keep HDBSCAN with explicit cold-start safeguards

**Why this is correct**

- HDBSCAN fits unknown-cluster-count problems and handles noise naturally.
- It avoids forcing all points into clusters, which improves trust in cluster quality.
- Running locally supports privacy and reproducibility goals.

**Risk**

- Sparse early cycles can produce mostly noise (few/no clusters) with strict thresholds.
- If unclustered items are hidden, users may think submissions were dropped.

**Guardrail**

1. Make `min_cluster_size` config/cycle driven with a v0 default of `5`; only tune via config/policy when sparse cycles require it.
2. Persist chosen clustering parameters in evidence metadata.
3. Surface unclustered candidates in analytics with clear explanation.

**Verdict**: **Keep with guardrail**
