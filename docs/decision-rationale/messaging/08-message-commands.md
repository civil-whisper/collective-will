# Decision Rationale — messaging/08-message-commands.md

> **Corresponds to**: [`docs/agent-context/messaging/08-message-commands.md`](../../agent-context/messaging/08-message-commands.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- All Telegram interaction is button-driven via inline keyboards (callback queries). No typed commands.
- This eliminates misinterpretation of user input (misspellings, unknown commands being treated as submissions).
- Router behavior runs on normalized `UnifiedMessage` data using the `callback_data` and `callback_query_id` fields.
- Endorsement callbacks use compact `e:{index}` format, not typed commands.
- Voting is per-policy with LLM-generated stance options, presented one policy at a time with a summary review page.

## Decision: Button-only UX over typed commands

**Why this is correct**

- Users don't need to memorize or type commands — reduces errors and support burden.
- Callback data encoding is compact and deterministic — no parsing ambiguity.
- Inline keyboards provide discoverability — all available actions visible at all times.
- State machine (`bot_state` + `bot_state_data`) persists across bot restarts.

**Risk**

- Inline keyboards are Telegram-specific; WhatsApp has limited interactive message support.
- `bot_state_data` JSONB could grow if not cleaned up after flow completion.

**Guardrail**

- Keep routing based on `BaseChannel` + `UnifiedMessage` — callback handling is dispatched generically.
- Always clear `bot_state` and `bot_state_data` on flow completion (submit, vote, cancel).
- `answer_callback()` and `edit_message_markup()` default to no-op on platforms without callback support.

**Verdict**: **Keep with guardrail**
