# Decision Rationale — messaging/09-telegram-test-channel.md

> **Corresponds to**: [`docs/agent-context/messaging/09-telegram-test-channel.md`](../../agent-context/messaging/09-telegram-test-channel.md)
>
> When a decision changes in either file, update the other.

---

## Context

WhatsApp (via Evolution API / Baileys) is the v0 production channel. Baileys uses
WhatsApp's unofficial Web protocol. WhatsApp actively detects and bans numbers
exhibiting automation patterns — making it unsuitable for repeated development
testing and local end-to-end smoke tests.

The original plan was to fire mock `curl` payloads at the local webhook for unit and
integration tests, and use a throwaway virtual number (e.g. SMSPVA) for the one-time
end-to-end smoke test. This works but has friction: every new developer needs to
acquire a throwaway number, ban events during active testing require number rotation,
and the WhatsApp session must be kept alive in Evolution API.

---

## Decision: Add TelegramChannel as a dev/test-only BaseChannel adapter

**Why this is correct**

- Telegram provides an **official Bot API** — no unofficial protocol, no ban risk,
  no number acquisition required. Setup takes under 5 minutes via @BotFather.
- A second real `BaseChannel` implementation **validates the abstraction under test**,
  not just with a mock. If the handlers and pipeline work correctly with
  `TelegramChannel`, they will work with `WhatsAppChannel` — the business logic
  is provably channel-agnostic.
- No identity exposure: Telegram bot tokens carry no real-world identity. No SIM
  card, no personal number, no Meta account linkage.
- Consistent with the existing CONTEXT-shared guardrail: *"enforce with
  fake/mock-channel tests so adding Signal/Telegram in v1 is a one-module
  addition."* This adapter is that one module, used earlier for dev convenience.

**Why this is not a production channel**

- v0 scope is WhatsApp-only. Telegram is explicitly out of scope for v0.
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

**Verdict**: **Approved for dev/test use; explicitly excluded from production**
