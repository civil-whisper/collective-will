# Task: Submission Intake Handler

## Depends on
- `messaging/03-webhook-endpoint` (message routing)
- `messaging/02-whatsapp-evolution-client` (WhatsAppChannel for sending confirmations)
- `database/03-core-models` (Submission model, User model, CRUD queries)
- `database/04-evidence-store` (append_evidence function)
- `pipeline/03-canonicalization` (canonicalize_single for inline processing)
- `pipeline/04-embeddings` (compute_and_store_embeddings for inline embedding)

## Goal
Implement the handler that receives a user's freeform text message, stores it as a submission, performs inline canonicalization and embedding, provides immediate feedback (including garbage rejection), and logs evidence.

## Files to create

- `src/handlers/intake.py` — submission intake handler

## Specification

### handle_submission()

```python
async def handle_submission(
    message: UnifiedMessage,
    user: User,
    channel: BaseChannel,
    db: AsyncSession,
) -> None:
```

Steps:
1. **Check eligibility**: User must be verified (`email_verified=True` AND `messaging_verified=True`) AND account age >= `settings.min_account_age_hours` (default 48 in production). If not eligible, send a locale-aware message explaining why and return.
2. **Check rate limit**: Query submissions by this user in the last 24 hours. If >= `MAX_SUBMISSIONS_PER_DAY`, send "limit reached" message and return.
3. **Run pre-persist PII screening**:
   - Detect high-risk personal identifiers in `message.text` (for example: phone numbers, emails, national IDs, exact addresses).
   - If high-risk PII is found: do not persist submission text. Send a locale-aware prompt asking the user to remove PII and resend.
   - Log only a minimal evidence event (reason code/flags, no raw content).
4. **Store submission**:
   - Compute `hash = sha256(raw_text)`
   - Create Submission record: `user_id`, `raw_text=message.text`, `language` (detect later), `status="pending"`, `hash`
   - Save to database
5. **Log to evidence store**: Append `submission_received` event with payload `{submission_id, user_id, raw_text, hash, timestamp}`
6. **Inline canonicalization** (wrapped in try/except for graceful degradation):
   - Call `canonicalize_single(submission, db)` which returns either a `PolicyCandidateCreate` or `CanonicalizationRejection`.
   - **If rejected** (`CanonicalizationRejection`):
     - Set `submission.status = "rejected"`
     - Log `submission_rejected_not_policy` evidence event
     - Send locale-aware rejection message including the LLM's contextual `rejection_reason` (in the user's input language)
     - Return (rejected submissions still count against daily quota)
   - **If valid** (`PolicyCandidateCreate`):
     - Create `PolicyCandidate` record in DB
     - Call `compute_and_store_embeddings([candidate], db)` for inline embedding
     - Set `submission.status = "canonicalized"`
     - Send locale-aware confirmation including the English canonical title
7. **LLM failure fallback**: If canonicalization or embedding raises an exception:
   - Keep `submission.status = "pending"` (batch scheduler will retry)
   - Send a generic locale-aware confirmation (without canonical title)
8. **Do not increment contribution_count here**: Contribution credit is added only after pipeline acceptance (`status="processed"`) or explicit policy endorsement.

### Locale-aware messaging

User-facing messages use the `user.locale` field to select language:
- Supported locales: `"fa"` (Farsi) and `"en"` (English), with English as default fallback.
- Messages are stored in a `_MESSAGES` dict keyed by locale and message key.
- A `_msg(locale, key, **kwargs)` helper selects and formats the correct template.
- Message keys: `confirmation`, `confirmation_fallback`, `rejection`, `pii_warning`, `not_eligible`, `rate_limit`.

### Hash computation

```python
import hashlib

def hash_submission(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

## Constraints

- Canonicalization and embedding run inline at submission time (not deferred to batch). The batch scheduler serves as a retry fallback for submissions that fail inline processing.
- Do NOT send the user's raw text to any external API except through the canonicalization pipeline (which uses `prepare_batch_for_llm` for privacy).
- The user_id in the evidence store payload is the internal UUID, NOT the messaging platform ID.
- If any step fails (DB write, evidence append), the submission should not be partially saved. Use a transaction.
- Keep this handler channel-agnostic: interact through `BaseChannel` only, never provider-specific methods or payload assumptions.
- Do not hardcode `48` in handler logic; use config (`MIN_ACCOUNT_AGE_HOURS`) so tests can lower the threshold safely.
- `contribution_count` must not be incremented on intake; only accepted contributions (processed submissions or endorsements) count.
- High-risk PII submissions must not be stored as `raw_text`; users are asked to redact and resend.
- PII-detected rejection logs must not include the user's raw content.
- Rejected garbage submissions still count against `MAX_SUBMISSIONS_PER_DAY` (anti-sybil: prevents abuse of LLM resources).

## Tests

Write tests in `tests/test_handlers/test_intake.py` covering:
- Valid submission from verified user: submission stored, canonicalized inline, evidence logged, confirmation with canonical title sent
- Unverified user (email not verified): submission rejected, appropriate message sent
- Unverified user (messaging not verified): submission rejected
- Account too young (< configured minimum): submission rejected
- With `MIN_ACCOUNT_AGE_HOURS=1` in test config, users older than 1 hour are accepted
- Rate limit: 5th submission accepted, 6th rejected with limit message
- High-risk PII detected: submission text is not stored; user receives redact-and-resend prompt
- PII-detection evidence event excludes raw submission content
- Garbage submission rejected: `canonicalize_single` returns `CanonicalizationRejection`, status set to `"rejected"`, rejection message sent with contextual reason
- LLM failure fallback: canonicalization raises exception, status stays `"pending"`, generic confirmation sent
- Submission hash is correct SHA-256 of raw_text
- Evidence log entry has correct event_type and payload
- User contribution_count is unchanged by intake (increment happens at acceptance/endorsement stage)
- Database transaction: if evidence append fails, submission is not saved (rollback)
- Mock the channel's send_message to verify confirmation message content
- Locale-aware messages: test both Farsi and English user locales
