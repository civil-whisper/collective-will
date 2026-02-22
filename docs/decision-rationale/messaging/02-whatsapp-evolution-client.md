# Decision Rationale — messaging/02-whatsapp-evolution-client.md

> **Corresponds to**: [`docs/agent-context/messaging/02-whatsapp-evolution-client.md`](../../agent-context/messaging/02-whatsapp-evolution-client.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This file is the concrete adapter for the shared-context channel decision:

- MVP testing transport is Telegram-first; WhatsApp Evolution is deferred post-MVP
- Evolution-specific payload knowledge is isolated to this module
- raw `wa_id` is confined to a sealed mapping layer; core app uses opaque `account_ref`
- all other layers consume only normalized abstractions (`UnifiedMessage`, `OutboundMessage`, `BaseChannel`)

---

## Decision: Implement WhatsApp as an edge adapter, not an app-wide dependency

**Why this is correct**

- Keeps provider-specific parsing and auth details confined to one module
- Prevents business logic from depending on Evolution webhook shape
- Preserves portability for future channels

**Risk**

- If raw payload assumptions leak out of this file, channel expansion becomes expensive and error-prone.
- Evolution API breakage has higher blast radius if adapter boundaries are weak.

**Guardrails**

- Only this module reads raw Evolution payload fields and raw `wa_id`.
- Mapping rule is `wa_id ↔ random opaque account_ref (UUID)`; no deterministic HMAC tokenization.
- Downstream code should accept normalized models and opaque refs only.

**Verdict**: **Keep with guardrail**
