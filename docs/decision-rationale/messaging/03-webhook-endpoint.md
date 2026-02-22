# Decision Rationale — messaging/03-webhook-endpoint.md

> **Corresponds to**: [`docs/agent-context/messaging/03-webhook-endpoint.md`](../../agent-context/messaging/03-webhook-endpoint.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Webhook endpoint is WhatsApp-specific in v0 (`/webhook/whatsapp`) by design.
- But this route must normalize payloads immediately and pass only `UnifiedMessage` downstream.

**Guardrail**: Keep Evolution payload parsing at the edge (`WhatsAppChannel.parse_webhook()`); routing logic remains provider-agnostic.
