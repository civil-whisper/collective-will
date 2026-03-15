# Decision Rationale — database/04-evidence-store.md

> **Corresponds to**: [`docs/agent-context/database/04-evidence-store.md`](../../agent-context/database/04-evidence-store.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements shared-context D19/D20 as:

- Append-only hash-chain evidence log remains the primary audit substrate.
- Daily Merkle-root computation is mandatory in v0.
- External timestamping/attestation is optional and config-driven.
- Entry hash material covers full entry fields (not payload-only) using canonical JSON serialization for reproducible third-party verification.

---

## Decision: Always compute local roots, optionally timestamp/publish externally

**Why this is correct**

- Removes the "optional means never" failure mode for anchoring readiness.
- Keeps verification logic continuously exercised in v0.
- Preserves launch flexibility by not hard-blocking on an external anchor service.

**Risk**

- Teams may compute roots but forget to monitor publication health once enabled.

**Guardrail**

- Treat root computation as a required daily job.
- Make only external timestamping/publication conditional.
- Evidence-log the full anchoring path: `anchor_publish_attempted`, `anchor_publish_succeeded`, `anchor_publish_failed` events tracked alongside `anchor_computed`.
- Evidence-log bundle export lifecycle: `audit_bundle_generated`, `audit_bundle_publish_succeeded`, `audit_bundle_publish_failed`.
- Hash full evidence entry material (`timestamp`, `event_type`, `entity_type`, `entity_id`, `payload`, `prev_hash`) with canonical serialization (sorted keys) so independent verifiers can reproduce hashes.

**Verdict**: **Keep with guardrail**

---

## Decision: Privacy-first audit visibility with user receipts

**Why this is correct**

- Three-tier visibility model (public_now, delayed, private_receipt_only) balances transparency with coercion resistance.
- Public API never exposes who took an action — only that actions occurred.
- Delayed fields (e.g., `vote_cast` selections) prevent vote-peeking during active cycles but become visible after tally.
- HMAC-based receipts give users provable inclusion without creating transferable identity proofs.
- Recursive PII stripping prevents nested field leaks.

**Risk**

- Delayed-field logic relies on correct cycle status tracking; stale cycle status could leak or over-redact.

**Guardrail**

- Evidence endpoint queries active cycle IDs at request time (not cached).
- Receipt tokens are HMAC-SHA256 bound to the evidence entry hash — stateless verification, no receipt table needed.
- Blockchain anchoring is explicitly deferred to later versions; OpenTimestamps-backed proof publication is the phase-1 external trust anchor.

**Verdict**: **Implemented as planned**
