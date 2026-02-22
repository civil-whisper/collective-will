# Task: WhatsApp Evolution API Client

## Depends on
- `messaging/01-channel-base-types` (BaseChannel, UnifiedMessage, OutboundMessage)
- `database/01-project-scaffold` (config with EVOLUTION_API_URL, EVOLUTION_API_KEY)

## Goal
Define the WhatsApp channel integration contract using Evolution API for post-MVP rollout. MVP build/testing uses Telegram first; this module remains the deferred transport adapter so migration can happen without business-logic rewrites.

## Files to create

- `src/channels/whatsapp.py` — WhatsAppChannel implementation

## Specification

### WhatsAppChannel class

```python
class WhatsAppChannel(BaseChannel):
    def __init__(self, api_url: str, api_key: str, mapping_repo: MappingRepository):
        self.api_url = api_url
        self.api_key = api_key
        self.mapping_repo = mapping_repo
        self.client = httpx.AsyncClient(
            base_url=api_url,
            headers={"apikey": api_key},
            timeout=30.0,
        )
```

### send_message()

POST to Evolution API endpoint to send a text message.
- Endpoint: `POST {api_url}/message/sendText/{instance}`
- Body: `{"number": wa_id, "text": message.text}`
- The recipient_ref in OutboundMessage is an opaque account ref. You must reverse-lookup raw `wa_id` from the sealed mapping to send.

### parse_webhook()

Parse the Evolution API webhook payload into a `UnifiedMessage`:
- Extract sender phone number from payload
- Resolve account ref from sealed mapping:
  - if `wa_id` exists, use existing `account_ref`
  - otherwise create `account_ref = str(uuid4())`, save `wa_id ↔ account_ref` in sealed mapping
- Extract message text (handle text messages only; ignore media, reactions, status updates)
- Return `None` for non-text-message payloads

Example Evolution API webhook payload structure:
```json
{
  "event": "messages.upsert",
  "instance": "default",
  "data": {
    "key": {
      "remoteJid": "989123456789@s.whatsapp.net",
      "fromMe": false,
      "id": "ABC123"
    },
    "message": {
      "conversation": "سلام، وضعیت اقتصادی خیلی بد است"
    },
    "messageTimestamp": 1707000000
  }
}
```

### Account reference mapping

```python
from uuid import uuid4

async def resolve_or_create_account_ref(wa_id: str, mapping_repo: MappingRepository) -> str:
    existing = await mapping_repo.get_ref_by_wa_id(wa_id)
    if existing is not None:
        return existing
    account_ref = str(uuid4())
    await mapping_repo.create_mapping(wa_id=wa_id, account_ref=account_ref)
    return account_ref
```

This mapping must be stable over time (same `wa_id` returns the same existing `account_ref`) while keeping refs non-derivable from phone numbers.

### send_ballot()

Format a voting ballot as a numbered list in Farsi and send via `send_message()`:

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

## Constraints

- NEVER log or store raw WhatsApp IDs (`wa_id`) in application tables, logs, or error messages. Only the opaque account ref.
- The raw ID mapping (`wa_id ↔ account_ref`) is needed only for messaging transport. Keep it in a separate, restricted table or service.
- Handle Evolution API errors gracefully (connection timeout, 4xx, 5xx). Return `False` from `send_message()` on failure, do not crash.
- Keep WhatsApp/Evolution-specific payload details isolated to this module; all other layers consume only `UnifiedMessage`, `OutboundMessage`, and `BaseChannel`.

## Tests

Write tests in `tests/test_channels/test_whatsapp.py` covering:
- `parse_webhook()` correctly extracts text and opaque sender_ref from a valid payload
- `parse_webhook()` returns None for status update payloads (no message text)
- `parse_webhook()` returns None for media messages
- `resolve_or_create_account_ref()` returns the existing ref for a known `wa_id`
- `resolve_or_create_account_ref()` creates a new UUID ref for unseen `wa_id`
- Different `wa_id` values produce different account refs
- `send_message()` calls the correct Evolution API endpoint (mock httpx)
- `send_message()` returns False on HTTP error (mock 500 response)
- `send_ballot()` formats the ballot correctly with numbered policies in Farsi
