# Task: Channel Base Class and Message Types

## Depends on
- `database/01-project-scaffold` (project structure exists)

## Goal
Create the abstract channel interface and unified message types. This is the foundation for all messaging integrations — Telegram first for MVP testing, WhatsApp next, Signal later. This abstraction is mandatory so transport changes are one-module updates.

## Files to create

- `src/channels/base.py` — abstract base class
- `src/channels/types.py` — unified message models

## Specification

### src/channels/types.py

```python
class UnifiedMessage(BaseModel):
    """Normalized incoming message from any platform."""
    text: str
    sender_ref: str              # Opaque account reference (never raw ID)
    platform: Literal["telegram", "whatsapp"]  # Extend to "signal" later
    timestamp: datetime
    message_id: str              # Platform-specific message ID
    raw_payload: dict | None = None  # Original webhook payload for debugging

class OutboundMessage(BaseModel):
    """Message to send to a user."""
    recipient_ref: str           # Opaque account reference
    text: str
    platform: Literal["telegram", "whatsapp"]
```

### src/channels/base.py

```python
from abc import ABC, abstractmethod

class BaseChannel(ABC):
    """Abstract interface for messaging platforms."""

    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> bool:
        """Send a message. Returns True if sent successfully."""
        ...

    @abstractmethod
    def parse_webhook(self, payload: dict) -> UnifiedMessage | None:
        """Parse incoming webhook payload into UnifiedMessage.
        Returns None if payload is not a user text message (e.g., status update)."""
        ...

    @abstractmethod
    async def send_ballot(self, recipient_ref: str, policies: list[dict]) -> bool:
        """Send a formatted voting ballot to a user."""
        ...
```

## Constraints

- `sender_ref` and `recipient_ref` are ALWAYS opaque references, never raw platform IDs.
- The `platform` field is a string literal, not a free-form string. This allows type checking.
- `parse_webhook` returns `None` for non-message payloads (delivery receipts, status updates, etc.) — these should be silently ignored, not raise errors.
- Downstream handlers and routers must depend on `BaseChannel` + `UnifiedMessage`, not on `WhatsAppChannel` concrete types.

## Tests

Write tests in `tests/test_channels/test_types.py` covering:
- `UnifiedMessage` validates correct input
- `UnifiedMessage` rejects missing required fields (text, sender_ref, platform, timestamp, message_id)
- `UnifiedMessage` rejects invalid platform value
- `OutboundMessage` validates correct input
- `BaseChannel` cannot be instantiated directly (ABC enforcement)
- A concrete subclass that implements all abstract methods can be instantiated
- A fake/mock channel implementing `BaseChannel` can be used in tests without importing `WhatsAppChannel`
