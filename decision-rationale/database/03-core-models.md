# Decision Rationale — database/03-core-models.md

> **Corresponds to**: [`docs/agent-context/database/03-core-models.md`](../../agent-context/database/03-core-models.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- `User.messaging_account_ref` stores a random opaque account ref (UUID), not raw `wa_id` and not deterministic HMAC output.
- Raw WhatsApp identifiers are excluded from ORM models and belong only in the sealed mapping store.
- `contribution_count` should represent both processed submissions and recorded policy endorsements.
- Add `PolicyEndorsement` as a first-class model so pre-ballot signatures are queryable and auditable.
- Keep ORM and Pydantic layers separate but connected via explicit conversion methods (`from_orm_model`, `to_schema`) with round-trip tests.
- `trust_score` should be treated as reserved unless an explicit v0 policy consumes it.
- `stance` semantics should distinguish descriptive/no-side content (`neutral`) from model uncertainty (`unclear`).
- Vote approval storage may remain array-based in v0, but per-cluster counting should be encapsulated behind query helpers to preserve migration flexibility.

## Decision: Keep opaque refs in core models

**Why this is correct**

- Limits blast radius from application DB leaks (refs are non-derivable from phone numbers).
- Preserves lookup simplicity (`get_user_by_messaging_ref`) without exposing transport identifiers.

**Guardrail**

- Maintain strict separation: core schema stores opaque refs; mapping service stores `wa_id ↔ account_ref`.
- Enforce unique `(user_id, cluster_id)` endorsement signatures to prevent duplicate signature inflation.
- Require explicit conversion methods between ORM and Pydantic models and validate field parity in tests.
- Keep `SQLModel` only as an evaluated option for reducing boilerplate; do not change architecture in v0 without an explicit decision update.
- Keep `trust_score` non-authoritative in v0 unless shared-context policy explicitly promotes it.
- Avoid direct storage-shape coupling for vote approvals; use query helpers so a future `vote_approval` junction-table migration is low-risk.

**Verdict**: **Keep with guardrail**
