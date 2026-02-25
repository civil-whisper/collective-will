# Task: Channel Base Class and Message Types

## Depends on
- `database/01-project-scaffold` (project structure exists)

## Goal
Create the abstract channel interface and unified message types. This is the foundation for all messaging integrations — Telegram first for MVP testing, WhatsApp next, Signal later. This abstraction is mandatory so transport changes are one-module updates. The interface supports both simple text messaging and interactive features (inline keyboards, callback queries).

## Files to create

- `src/channels/base.py` — abstract base class
- `src/channels/types.py` — unified message models
- `src/channels/telegram.py` — Telegram Bot API implementation
- `src/channels/whatsapp.py` — WhatsApp Evolution API implementation (post-MVP)

## Specification

### src/channels/types.py

```python
class UnifiedMessage(BaseModel):
    """Normalized incoming message from any platform."""
    text: str
    sender_ref: str              # Opaque account reference (never raw ID)
    platform: Literal["telegram", "whatsapp"]
    timestamp: datetime
    message_id: str              # Platform-specific message ID
    raw_payload: dict | None = None
    callback_data: str | None = None        # Inline keyboard callback payload
    callback_query_id: str | None = None    # Platform callback query ID (for acknowledgement)

class OutboundMessage(BaseModel):
    """Message to send to a user."""
    recipient_ref: str           # Opaque account reference
    text: str
    platform: Literal["telegram", "whatsapp"]
    reply_markup: dict | None = None        # Inline keyboard definition (Telegram format)
```

### src/channels/base.py

```python
from abc import ABC, abstractmethod

class BaseChannel(ABC):
    """Abstract interface for messaging platforms."""

    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> bool:
        """Send a message (with optional inline keyboard via reply_markup).
        Returns True if sent successfully."""
        ...

    @abstractmethod
    async def parse_webhook(self, payload: dict) -> UnifiedMessage | None:
        """Parse incoming webhook payload into UnifiedMessage.
        Returns None if payload is not a user text message or callback query."""
        ...

    async def answer_callback(self, callback_query_id: str, text: str | None = None) -> bool:
        """Acknowledge an inline-keyboard callback tap. Platforms without
        callback support return False by default."""
        return False

    async def edit_message_markup(
        self, recipient_ref: str, message_id: str, reply_markup: dict
    ) -> bool:
        """Edit the inline keyboard on an existing message. Platforms without
        inline keyboard support return False by default."""
        return False
```

Note: `send_ballot()` has been removed from the base interface. Ballot rendering is now handled by `commands.py` using `send_message()` with `reply_markup` inline keyboards.

### TelegramChannel Implementation

`src/channels/telegram.py` implements `BaseChannel` for the Telegram Bot API:

- `parse_webhook()`: Handles both `message` and `callback_query` payloads. For callbacks, extracts `callback_data` and `callback_query_id` into `UnifiedMessage`.
- `send_message()`: Sends via Telegram `sendMessage` API, passing `reply_markup` as the inline keyboard when present.
- `answer_callback()`: Calls `answerCallbackQuery` to dismiss the loading indicator on the client.
- `edit_message_markup()`: Calls `editMessageReplyMarkup` to update inline keyboards on existing messages.

## Constraints

- `sender_ref` and `recipient_ref` are ALWAYS opaque references, never raw platform IDs.
- The `platform` field is a string literal, not a free-form string.
- `parse_webhook` returns `None` for non-message payloads (delivery receipts, status updates, etc.).
- `callback_data` and `callback_query_id` are only populated for inline keyboard callback events.
- `answer_callback()` and `edit_message_markup()` have concrete default implementations (return `False`) so platforms without interactive keyboard support don't need to override them.
- Downstream handlers and routers must depend on `BaseChannel` + `UnifiedMessage`, not on concrete channel types.

## Tests

Tests in `tests/test_channels/test_types.py` and `tests/test_channels/test_telegram.py` covering:
- `UnifiedMessage` validates correct input (including callback fields)
- `UnifiedMessage` rejects missing required fields
- `OutboundMessage` validates correct input (including reply_markup)
- `BaseChannel` cannot be instantiated directly (ABC enforcement)
- A concrete subclass implementing abstract methods can be instantiated
- A FakeChannel implementing `BaseChannel` can drive handler logic without importing platform-specific channels
- TelegramChannel `parse_webhook` handles both text messages and callback queries
- TelegramChannel `send_message` passes reply_markup to Telegram API
- TelegramChannel `answer_callback` calls answerCallbackQuery
