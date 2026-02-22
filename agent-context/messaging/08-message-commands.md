# Task: Message Command Router

## Depends on
- `messaging/03-webhook-endpoint` (route_message stub)
- `messaging/04-submission-intake` (handle_submission)
- `messaging/07-voting-service` (cast_vote, parse_ballot)
- `messaging/02-whatsapp-evolution-client` (WhatsAppChannel)
- `database/03-core-models` (User, Submission, VotingCycle queries)

## Goal
Implement the message router that detects whether an incoming WhatsApp message is a command or a freeform submission, and dispatches accordingly. The routing logic should stay channel-agnostic so adding a second channel in v1 does not require rewriting command handling.

## Files to create/modify

- `src/handlers/commands.py` — command detection and routing
- Update `src/api/routes/webhooks.py` — replace `route_message` stub with real implementation

## Specification

### Commands

| User Input | Action |
|------------|--------|
| `وضعیت` or `status` | Show pending submissions count, active voting cycle status |
| `کمک` or `help` | Show available commands |
| `رای` or `vote` | Show current voting agenda (if active cycle exists) |
| `امضا 3` or `sign 3` | Record pre-ballot endorsement/signature for listed agenda item |
| `زبان` or `language` | Toggle locale between Farsi and English, persist to user record |
| `انصراف` or `skip` | Skip current voting cycle (acknowledge, do nothing) |
| `1, 3, 5` (numbers during active vote) | Parse as ballot and cast vote |
| Any other freeform text | Route to submission intake |

### Command detection

```python
def detect_command(text: str) -> str | None:
    """Returns command name if text matches a known command, else None."""
```

- Normalize: strip whitespace, lowercase for English commands
- Check Farsi commands first, then English equivalents
- During an active voting cycle, check if text looks like a ballot (comma/space-separated numbers) before treating as command or submission
- During pre-ballot endorsement window, support `sign <number>` / `امضا <شماره>` for endorsement recording

### route_message() implementation

Replace the stub in webhooks.py:

```python
async def route_message(message: UnifiedMessage, db: AsyncSession) -> None:
    # 1. Look up user by messaging_account_ref
    # 2. If user not found and message matches linking code pattern → handle linking
    # 3. If user not found → send "please register first" message
    # 4. Detect command
    # 5. If command → dispatch to command handler
    # 6. If pre-ballot stage and message is sign command → dispatch to record_endorsement
    # 7. If active voting cycle and text looks like ballot → dispatch to voting
    # 8. Else → dispatch to submission intake
```

### Command responses (Farsi primary)

**status** response:
```
📊 وضعیت شما:
ارسالی‌ها: {count} ({pending} در انتظار)
رای‌گیری فعال: {yes/no}
```

**help** response:
```
🔹 دستورات:
وضعیت — وضعیت حساب شما
رای — مشاهده رای‌گیری فعال
زبان — تغییر زبان
انصراف — رد کردن رای‌گیری
یا هر متنی بفرستید تا نگرانی شما ثبت شود.
```

**vote** response:
- If active cycle: send ballot via `send_ballot_prompt()`
- If no active cycle: `"در حال حاضر رای‌گیری فعالی وجود ندارد."` ("No active voting cycle.")

**sign** response:
- If pre-ballot endorsement list is open: record endorsement and confirm `"✅ امضای شما ثبت شد."`
- If not in pre-ballot stage: return `"در حال حاضر مرحله امضا فعال نیست."`

**language** response:
- Toggle user.locale between "fa" and "en"
- Confirm: `"Language changed to English."` or `"زبان به فارسی تغییر کرد."`

**skip** response:
- `"✅ از این دور رای‌گیری رد شدید."` ("You skipped this voting cycle.")

## Constraints

- Command detection must handle both Farsi and English variants.
- During active voting, a message like `"1, 3"` should be parsed as a ballot, NOT as a submission.
- Endorsement commands (`sign 3` / `امضا ۳`) are only valid during pre-ballot stage.
- Unknown users (no account linked) should receive a clear message directing them to register via the website.
- All responses should be in the user's preferred locale (`user.locale`), defaulting to Farsi.
- Keep command routing based on normalized `UnifiedMessage`; avoid WhatsApp-specific payload checks in router logic.

## Tests

Write tests in `tests/test_handlers/test_commands.py` covering:
- `detect_command("وضعیت")` returns `"status"`
- `detect_command("status")` returns `"status"`
- `detect_command("STATUS")` returns `"status"` (case-insensitive English)
- `detect_command("کمک")` returns `"help"`
- `detect_command("امضا 3")` returns `"sign"`
- `detect_command("1, 3, 5")` returns None (not a command — handled separately as ballot)
- `detect_command("I am worried about inflation")` returns None (freeform text)
- `route_message` dispatches status command to status handler (mock handlers)
- `route_message` dispatches freeform text to submission intake
- `route_message` dispatches sign command to endorsement handler during pre-ballot stage
- `route_message` dispatches ballot-like text to voting during active cycle
- `route_message` sends registration prompt for unknown users
- Language toggle persists to user record
- Each command responds with the correct Farsi message content (verify via mock channel)
