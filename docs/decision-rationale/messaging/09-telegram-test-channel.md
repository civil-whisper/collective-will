# Decision Rationale — messaging/09-telegram-test-channel.md

> **Corresponds to**: [`docs/agent-context/messaging/09-telegram-test-channel.md`](../../agent-context/messaging/09-telegram-test-channel.md)
>
> When a decision changes in either file, update the other.

---

## Context

WhatsApp (via Evolution API / Baileys) remains the target rollout channel, but
anonymous Netherlands SIMs required for safe operations are still in transit.
Until SIM operations are ready, Telegram is used as the primary MVP testing
transport to keep implementation velocity high.

The original plan was to fire mock `curl` payloads at the local webhook for unit and
integration tests, and use a throwaway virtual number (e.g. SMSPVA) for the one-time
end-to-end smoke test. This works but has friction: every new developer needs to
acquire a throwaway number, ban events during active testing require number rotation,
and the WhatsApp session must be kept alive in Evolution API.

---

## Decision: Use TelegramChannel as the primary MVP testing adapter

**Why this is correct**

- Telegram provides an **official Bot API** — no unofficial protocol, no ban risk,
  and no SIM provisioning dependency. Setup takes under 5 minutes via @BotFather.
- A second real `BaseChannel` implementation **validates the abstraction under test**,
  not just with a mock. If the handlers and pipeline work correctly with
  `TelegramChannel`, they will work with `WhatsAppChannel` — the business logic
  is provably channel-agnostic.
- No identity exposure: Telegram bot tokens carry no real-world identity. No SIM
  card, no personal number, no Meta account linkage.
- Keeps the shared guardrail intact: *transport logic stays behind `BaseChannel`*,
  so switching from Telegram-first MVP testing to WhatsApp post-MVP is a bounded
  adapter change.

**Why this is still not final production policy**

- Telegram's default group/bot messages are not end-to-end encrypted; metadata
  is visible to Telegram servers. For the Iran pilot, routing real user submissions
  through Telegram introduces surveillance risk that WhatsApp (with E2E encryption
  on by default) does not.
- Pavel Durov's 2024 arrest and ongoing negotiations between Telegram and
  governments (including Iran) create long-term trust and compliance risk for a
  politically sensitive project.
- Adding Telegram as a production channel is a v1 decision that requires its own
  threat model review, not a consequence of this adapter existing.

**Risk**

- A developer could wire `TelegramChannel` into production config by mistake,
  exposing a live webhook endpoint and routing real user data through Telegram.

**Guardrails**

- `TelegramChannel` is only instantiated when `settings.telegram_bot_token` is
  set. This env var must be absent from all production `.env` files.
- The `/webhook/telegram` route returns HTTP 404 when the token is not configured.
- `messaging_platform = "telegram"` must never appear in production user records.
- Raw Telegram `chat_id` follows the same sealed-mapping privacy rule as `wa_id`:
  confined to the mapping layer, never in application tables, logs, or error output.
- No Telegram-specific logic outside `src/channels/telegram.py` and its webhook
  route. All handlers and pipeline modules interact through `BaseChannel` only.

**Verdict**: **Approved as MVP testing transport; keep post-MVP migration path to WhatsApp**
