# Decision Rationale — pipeline/03-canonicalization.md

> **Corresponds to**: [`docs/agent-context/pipeline/03-canonicalization.md`](../../agent-context/pipeline/03-canonicalization.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- D8 is now Sonnet-first for canonicalization.
- Goal is extraction quality and operational simplicity, not lowest per-call cost.
- Canonicalization runs **inline at submission time** (not only in batch) for immediate user feedback.
- All canonical output (`title`, `summary`, `entities`) is always in English regardless of input language.
- Garbage/non-policy submissions are rejected at canonicalization time with feedback in the user's input language.

## Decision: Inline single-model Sonnet canonicalization with validity assessment

**Why this is correct**

- Better handling of nuanced Farsi political text, reducing downstream clustering errors.
- Inline processing provides immediate feedback: users see what the system understood, or why their submission was rejected.
- English-only canonical output ensures consistent embeddings and clustering across multilingual inputs.
- Garbage rejection at submission time saves pipeline resources and prevents abuse of LLM-intensive downstream stages.
- Simpler operations than multi-model adjudication/routing in v0.
- Cleaner audit trail: one primary model for canonicalization outputs.

**Why inline + batch fallback**

- Inline canon gives 2-5s turnaround in messaging apps, which is acceptable UX.
- If the LLM is unavailable at submission time, the submission stays `status="pending"` and the batch scheduler retries — no data loss.
- Rejected garbage submissions still count against `MAX_SUBMISSIONS_PER_DAY`, preventing sybil attacks that drain LLM resources.

**Risk**

- Model outage can delay processing (but not lose data — fallback to batch).
- High-quality models can still produce schema-invalid JSON intermittently.
- LLM latency at submission time (~2-5s) adds delay to messaging flow.

**Guardrail**

1. Strict JSON schema validation before saving candidates.
2. Automatic review path for low-confidence outputs.
3. Haiku fallback only for continuity, with fallback results explicitly flagged.
4. Graceful degradation: inline failure → status="pending" → batch retries.
5. `rejection_reason` in input language so user understands why their submission was rejected.

**Verdict**: **Keep with guardrail**
