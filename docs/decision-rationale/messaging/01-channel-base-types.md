# Decision Rationale — messaging/01-channel-base-types.md

> **Corresponds to**: [`docs/agent-context/messaging/01-channel-base-types.md`](../../agent-context/messaging/01-channel-base-types.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This task implements the cross-cutting channel decision from shared context:

- v0 remains **WhatsApp-only**
- but messaging architecture stays **multi-channel ready** via `BaseChannel`
- and this boundary is enforced with tests using fake/mock channel implementations

---

## Decision: Keep `BaseChannel` as the required boundary in v0

**Why this is correct**

- Limits WhatsApp lock-in to one adapter module (`src/channels/whatsapp.py`)
- Keeps handlers (`intake`, `voting`, `commands`) reusable across future channels
- Makes v1 expansion to Telegram/Signal a low-risk incremental change

**Risk if not enforced**

- WhatsApp payload assumptions leak into handlers and router logic
- Future second-channel support requires refactoring many modules instead of one
- Test coverage becomes provider-coupled and fragile

**Guardrail**

- Tests must prove that a fake class implementing `BaseChannel` can drive handler logic without importing `WhatsAppChannel`.

**Verdict**: **Keep with guardrail**
