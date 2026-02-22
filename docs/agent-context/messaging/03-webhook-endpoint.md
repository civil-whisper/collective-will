# Task: Webhook Endpoint

## Depends on
- `messaging/02-whatsapp-evolution-client` (WhatsAppChannel)
- `database/02-db-connection` (session dependency)
- `database/06-docker-compose` (FastAPI app exists at src/api/main.py)

## Goal
Create the FastAPI webhook route that receives Evolution API callbacks, validates them, and routes to the appropriate handler. Keep WhatsApp specifics at the edge and hand off a normalized `UnifiedMessage` to channel-agnostic routing logic.

## Files to create/modify

- `src/api/routes/webhooks.py` — webhook route
- `src/api/main.py` — register the webhook router

## Specification

### POST /webhook/whatsapp

```python
@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
```

Steps:
1. Parse the raw request body as JSON
2. Validate the Evolution API key from headers (compare against `settings.evolution_api_key`)
3. Pass payload to `WhatsAppChannel.parse_webhook()`
4. If `parse_webhook()` returns `None`, return 200 (acknowledge but ignore)
5. If it returns a `UnifiedMessage`, dispatch to the message router (implemented in later tasks — for now, just log and return 200)
6. Return 200 quickly. Heavy processing should happen in background tasks, not block the webhook response.

### Request validation

Check the `apikey` header (or whichever header Evolution API uses for authentication) against the expected key. Return 401 if it doesn't match.

### Message routing stub

Create a stub function that will be filled in by later tasks:

```python
async def route_message(message: UnifiedMessage, db: AsyncSession) -> None:
    """Route incoming message to appropriate handler.
    Will be implemented by messaging/08-message-commands task."""
    pass
```

Use FastAPI `BackgroundTasks` to run `route_message` without blocking the webhook response.

### Error handling

- Malformed JSON → 400
- Invalid API key → 401
- Internal error → 500 (log error, don't expose details)
- Always return quickly to avoid Evolution API retries

## Constraints

- The webhook must return 200 within a few seconds. Do NOT do heavy processing synchronously.
- Do NOT expose internal error details in the response body.
- Log the raw payload for debugging, but strip any raw wa_id before logging (log only the opaque account ref).
- Keep Evolution-specific parsing in `WhatsAppChannel.parse_webhook()`; downstream routing should operate on `UnifiedMessage`, not provider payload shape.

## Tests

Write tests in `tests/test_api/test_webhooks.py` covering:
- Valid webhook payload returns 200
- Invalid/missing API key returns 401
- Malformed JSON body returns 400
- Non-message payload (status update) returns 200 with no processing
- Valid text message payload triggers `route_message` (mock the handler, verify it's called with correct UnifiedMessage)
- Use FastAPI `TestClient` (or `httpx.AsyncClient` with `ASGITransport`)
