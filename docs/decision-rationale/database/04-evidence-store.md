# Decision Rationale — database/04-evidence-store.md

> **Corresponds to**: [`docs/agent-context/database/04-evidence-store.md`](../../agent-context/database/04-evidence-store.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements shared-context D19/D20 as:

- Append-only hash-chain evidence log remains the primary audit substrate.
- Daily Merkle-root computation is mandatory in v0.
- External Witness publication is optional and config-driven.
- Entry hash material covers full entry fields (not payload-only) using canonical JSON serialization for reproducible third-party verification.

---

## Decision: Always compute local roots, optionally publish externally

**Why this is correct**

- Removes the "optional means never" failure mode for anchoring readiness.
- Keeps verification logic continuously exercised in v0.
- Preserves launch flexibility by not hard-blocking on an external anchor service.

**Risk**

- Teams may compute roots but forget to monitor publication health once enabled.

**Guardrail**

- Treat root computation as a required daily job.
- Make only publication conditional (`WITNESS_PUBLISH_ENABLED`).
- Evidence-log the full anchoring path: computed root, publication attempt/result, and anchor receipt when present.
- Hash full evidence entry material (`timestamp`, `event_type`, `entity_type`, `entity_id`, `payload`, `prev_hash`) with canonical serialization (sorted keys) so independent verifiers can reproduce hashes.

**Verdict**: **Keep with guardrail**
