# Task: Telegram Channel Adapter (Dev/Test Only)

## Depends on
- `messaging/01-channel-base-types` (BaseChannel, UnifiedMessage, OutboundMessage)
- `database/01-project-scaffold` (config with TELEGRAM_BOT_TOKEN)

## Goal

Implement a `TelegramChannel(BaseChannel)` adapter to use during local development and
end-to-end testing in place of WhatsApp. Telegram's official Bot API has no ban risk,
requires no unofficial protocol, and can be set up in minutes — making it the right
channel for smoke-testing the full message intake, voting, and command flow before
connecting Evolution API.

**This is a dev/test adapter only.** It is not a v0 production channel. WhatsApp
remains the sole user-facing channel. The adapter must be excluded from production
config and clearly gated by `settings.env == "development"` or equivalent.

## Files to create

- `src/channels/telegram.py` — TelegramChannel implementation
- `tests/test_channels/test_telegram.py` — tests

## One-time setup (do once, outside code)

1. Open Telegram and message `@BotFather`
2. Send `/newbot`, follow prompts, get the bot token
3. Add `TELEGRAM_BOT_TOKEN=<token>` to `.env`
4. Set your webhook: `POST https://api.telegram.org/bot<TOKEN>/setWebhook?url=<your-ngrok-or-tunnel-url>/webhook/telegram`

## Specification

### Config addition

Add to `src/config.py`:

```python
telegram_bot_token: str | None = None   # dev/test only; absent in production
```

### TelegramChannel class

```python
class TelegramChannel(BaseChannel):
    def __init__(self, bot_token: str, mapping_repo: MappingRepository):
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.mapping_repo = mapping_repo
        self.client = httpx.AsyncClient(timeout=30.0)
```

### send_message()

POST to the Telegram Bot API to send a text message.

- Endpoint: `POST {api_url}/sendMessage`
- Body: `{"chat_id": chat_id, "text": message.text}`
- `message.recipient_ref` is an opaque account ref; reverse-lookup raw `chat_id`
  from the sealed mapping before sending.
- Return `False` on any HTTP error; do not raise.

### parse_webhook()

Parse the Telegram webhook payload into a `UnifiedMessage`:

- Extract `chat.id` (string) as the raw platform identifier
- Resolve or create opaque `account_ref` via `resolve_or_create_account_ref()`
  (same pattern as WhatsApp — raw chat ID lives only in sealed mapping)
- Extract `message.text`; return `None` for non-text updates (photos, stickers,
  edited messages, channel posts, etc.)
- Return `None` if `message` key is absent in the payload

Example Telegram webhook payload:
```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 42,
    "from": {"id": 987654321, "is_bot": false, "first_name": "Test"},
    "chat": {"id": 987654321, "type": "private"},
    "date": 1707000000,
    "text": "وضعیت اقتصادی خیلی بد است"
  }
}
```

### Account reference mapping

Reuse the same opaque-ref pattern as WhatsApp:

```python
async def resolve_or_create_account_ref(
    chat_id: str, mapping_repo: MappingRepository
) -> str:
    existing = await mapping_repo.get_ref_by_platform_id(
        platform="telegram", platform_id=chat_id
    )
    if existing is not None:
        return existing
    account_ref = str(uuid4())
    await mapping_repo.create_mapping(
        platform="telegram", platform_id=chat_id, account_ref=account_ref
    )
    return account_ref
```

Note: the sealed mapping table may need a `platform` column added if it currently
stores only `wa_id`. Extend it rather than duplicating the table.

### send_ballot()

Format a voting ballot and send via `send_message()`. Use the same Farsi template
as WhatsAppChannel:

```
🗳️ صندوق رای باز است!

این هفته، این سیاست‌ها مطرح شدند:

1. [Policy summary]
2. [Policy summary]
3. [Policy summary]

برای رای دادن، شماره‌های موردنظر خود را بفرستید.
مثال: 1, 3

برای انصراف: "انصراف" بفرستید
```

### Webhook route addition

Add a `/webhook/telegram` route in `src/api/routes/webhooks.py` alongside the
existing WhatsApp webhook. Gate it:

```python
if settings.telegram_bot_token is None:
    raise HTTPException(status_code=404)
```

This ensures the route is unreachable in production where the token is absent.

## Type model update

In `src/channels/types.py`, extend the platform literal:

```python
platform: Literal["whatsapp", "telegram"]
```

Also update `OutboundMessage.platform` the same way.

The `User.messaging_platform` field in the data model remains `"whatsapp"` for v0
production users. Telegram-sourced users in dev/test have `messaging_platform =
"telegram"` but these accounts never exist in production.

## Constraints

- NEVER log or store raw Telegram chat IDs (`chat_id`) in application tables, logs,
  or error messages. Only the opaque account ref — same rule as `wa_id`.
- This adapter must not be instantiated when `settings.telegram_bot_token is None`.
- All business logic (handlers, pipeline, voting) must continue to interact via
  `BaseChannel` only — they must not know or care whether the channel is Telegram
  or WhatsApp.
- Do not add Telegram-specific logic outside `src/channels/telegram.py` and its
  webhook route.
- This adapter is not shipped to production. Production config omits
  `TELEGRAM_BOT_TOKEN`.

## How to use for end-to-end testing

1. Start the local stack (`docker compose up`)
2. Expose your local server with `ngrok http 8000` (or equivalent)
3. Register the webhook URL with Telegram (one-time, see setup above)
4. Send a message to your bot in Telegram
5. Observe the full pipeline: webhook → intake → canonicalization → evidence log

This validates the complete message flow without touching Evolution API or risking
a WhatsApp ban.

## Tests

Write tests in `tests/test_channels/test_telegram.py` covering:

- `parse_webhook()` correctly extracts text and opaque sender_ref from a valid payload
- `parse_webhook()` returns `None` for photo message payloads (no `text` field)
- `parse_webhook()` returns `None` for edited message payloads
- `parse_webhook()` returns `None` when `message` key is absent (channel post, etc.)
- `resolve_or_create_account_ref()` returns existing ref for a known `chat_id`
- `resolve_or_create_account_ref()` creates a new UUID ref for an unseen `chat_id`
- Different `chat_id` values produce different account refs
- Same `chat_id` on repeated calls returns the same ref (idempotent)
- `send_message()` calls the correct Telegram endpoint (mock httpx)
- `send_message()` returns `False` on HTTP 4xx/5xx (mock error response)
- `send_ballot()` formats the ballot correctly with numbered policies in Farsi
- Webhook route returns 404 when `telegram_bot_token` is not configured
