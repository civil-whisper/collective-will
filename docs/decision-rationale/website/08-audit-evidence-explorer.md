# Decision Rationale — website/08-audit-evidence-explorer.md

> **Corresponds to**: [`docs/agent-context/website/08-audit-evidence-explorer.md`](../../agent-context/website/08-audit-evidence-explorer.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements evidence-chain verification guardrails as:

- Browser verification recomputes hash from full canonical entry material, not payload-only.
- Canonical serialization format is documented so independent verifiers can reproduce hashes exactly.
- Chain verification checks both hash integrity and `prev_hash` linkage.
- Daily audit snapshot pages separate bundle/proof verification from the live evidence explorer so ordinary users are not forced into raw-file workflows.
- The dedicated public verification guide keeps the auditor workflow discoverable without pushing all users into CLI-first UX.

---

## Decision: Reproducible client-side evidence verification

**Why this is correct**

- Matches shared-context tamper-evidence guarantees.
- Prevents silent metadata tampering that payload-only hashing would miss.
- Lets technical users verify integrity without trusting server-side claims.

**Guardrail**

- Keep client/server hash material and canonical serialization strictly identical.
- Include metadata-tamper test cases in verifier tests (not just payload tamper).
- Keep the auditor flow downloadable and reproducible, but do not make shell/CLI steps the primary public UX.
- Keep public links from receipts, audit snapshots, and footer navigation pointing to the same guide so verification help is easy to find.

**Verdict**: **Keep with guardrail**
