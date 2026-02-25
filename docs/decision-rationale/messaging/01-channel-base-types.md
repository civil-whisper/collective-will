# Decision Rationale — messaging/01-channel-base-types.md

> **Corresponds to**: [`docs/agent-context/messaging/01-channel-base-types.md`](../../agent-context/messaging/01-channel-base-types.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This task implements the cross-cutting channel decision from shared context:

- MVP build/testing is **Telegram-first**
- WhatsApp integration is **deferred post-MVP**
- but messaging architecture stays **multi-channel ready** via `BaseChannel`
- and this boundary is enforced with tests using fake/mock channel implementations

---

## Decision: Keep `BaseChannel` as the required boundary in v0

**Why this is correct**

- Limits transport lock-in to one adapter module at a time
- Keeps handlers (`intake`, `voting`, `commands`) reusable across future channels
- Keeps Telegram-first MVP testing and post-MVP WhatsApp rollout low-risk

**Risk if not enforced**

- Platform payload assumptions leak into handlers and router logic
- Future second-channel support requires refactoring many modules instead of one
- Test coverage becomes provider-coupled and fragile

**Guardrail**

- Tests must prove that a fake class implementing `BaseChannel` can drive handler logic without importing `TelegramChannel`.
- `answer_callback()` and `edit_message_markup()` are concrete methods with default no-op returns (`False`) so platforms without interactive keyboard support don't need to override them.
- `UnifiedMessage` carries `callback_data` and `callback_query_id` as optional fields — platforms that don't support callbacks simply leave them `None`.

**Verdict**: **Keep with guardrail**
