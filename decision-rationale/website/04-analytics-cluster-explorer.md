# Decision Rationale — website/04-analytics-cluster-explorer.md

> **Corresponds to**: [`docs/agent-context/website/04-analytics-cluster-explorer.md`](../../agent-context/website/04-analytics-cluster-explorer.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Analytics must show both clustered results and unclustered/noise candidates.
- This preserves transparency when HDBSCAN leaves sparse-cycle points unclustered.

## Decision: Expose unclustered candidates publicly (anonymized)

**Why this is correct**

- Prevents false perception that user submissions were discarded.
- Makes cold-start clustering behavior understandable and auditable.
- Supports trust without compromising privacy (canonicalized/anonymized display only).

**Guardrail**

- Always show unclustered counts and anonymized candidate list in analytics.
- Never show raw text or user identifiers in this section.

**Verdict**: **Keep with guardrail**
