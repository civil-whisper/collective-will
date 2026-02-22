# Decision Rationale — messaging/08-message-commands.md

> **Corresponds to**: [`docs/agent-context/messaging/08-message-commands.md`](../../agent-context/messaging/08-message-commands.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Commands are currently triggered from WhatsApp messages in v0.
- Router behavior should still run on normalized `UnifiedMessage` data to keep command logic reusable.
- Include explicit pre-ballot endorsement commands (`sign <n>` / `امضا <n>`) so users can contribute without creating new submissions.

**Guardrail**: Do not inspect Evolution raw payload shape inside command routing, and allow endorsement commands only during pre-ballot stage.
