# Task: Voice Signature Verification

## Depends on
- `messaging/01-channel-base-types` (`BaseChannel.download_file`, `UnifiedMessage.voice_file_id`)
- `messaging/08-message-commands` (voice gate in `route_message`, bot states)
- `messaging/09-telegram-test-channel` (`TelegramChannel.download_file`)
- `database/03-core-models` (User model: voice columns)
- `database/04-evidence-store` (`voice_enrolled`, `voice_enroll_phrase_rejected`, `voice_verified` event types)

## Goal

Verify user identity via voice biometrics before allowing high-trust actions (submit, vote, endorse). Users read randomized phrases aloud; the system compares speaker embeddings (ECAPA2 via Modal) and transcription accuracy (OpenAI GPT-4o-transcribe) against stored enrollment data. This dual-verification approach prevents both replay attacks and voice impersonation while remaining accessible over standard messaging voice notes.

## Architecture

Cloud-based: no local voice-service container.

1. User sends voice via Telegram -> backend downloads audio
2. Backend calls OpenAI GPT-4o-transcribe (transcription) and Modal ECAPA2 (embedding) in parallel
3. Backend scores transcription locally (word-overlap EN / subsequence+homophone FA)
4. Dual-check decision matrix: embedding similarity + transcription score -> accept/reject

## Files

### Voice module (`src/voice/`)

- `src/voice/__init__.py` -- package marker
- `src/voice/client.py` -- `VoiceCloudClient`: orchestrates OpenAI transcription + Modal embedding in parallel, scores locally
- `src/voice/transcription.py` -- OpenAI GPT-4o-transcribe API client (`transcribe_audio`)
- `src/voice/embedding.py` -- Modal serverless embedding API client (`get_speaker_embedding`)
- `src/voice/transcription_scoring.py` -- Word-overlap (EN) and subsequence+homophone (FA) scoring, ported from old voice-service
- `src/voice/audio.py` -- `download_and_validate_audio`, `AudioValidationError`: duration checks + channel download
- `src/voice/phrases.py` -- Loads phrase pools from external JSON file (`voice-phrases.json`), `select_phrases`, `get_phrase`, `pool_size` (uses `secrets` for selection)
- `src/voice/scoring.py` -- `cosine_similarity`, `voice_decision` (decision matrix), `serialize_embedding`, `deserialize_embedding`, `average_embeddings`
- `src/voice/enrollment.py` -- Multi-step enrollment state machine: `init_enrollment_state`, `start_enrollment`, `get_current_phrase`, `process_enrollment_audio`, `finalize_enrollment`; stores collected audio for model portability
- `src/voice/verification.py` -- Session verification: `pick_verification_phrase`, `verify_voice` (returns `VerificationOutcome` tuple)
- `src/voice/errors.py` -- `VoiceErrorCode` literal type and descriptions for technical error codes (V002–V004); duration validation uses user-facing messages, not codes
- `src/voice/crypto.py` -- Fernet encryption/decryption for voice embeddings at rest (`VOICE_ENCRYPTION_KEY`); backward-compatible with unencrypted legacy data

### Modal serverless function

- `modal_functions/voice_embedding.py` -- Modal serverless function: ECAPA2 speaker embedding (192-dim), CPU-only, model baked into image

### Enrollment audio storage

- `src/models/enrollment_audio.py` -- `EnrollmentAudio` SQLAlchemy model: stores raw OGG audio per enrollment phrase for model portability
- `migrations/versions/001_initial_schema.py` -- Includes the `enrollment_audio` table in the squashed baseline

### Modified files

- `src/models/user.py` -- Voice columns: `voice_enrolled_at`, `voice_verified_at`, `voice_embedding` (LargeBinary), `voice_model_version`
- `src/handlers/commands.py` -- Voice gate in `route_message`, enrollment/verification handlers, i18n strings (FA/EN), session extension on vote/endorse
- `src/channels/base.py` -- Abstract method `download_file(file_id: str) -> bytes`
- `src/channels/types.py` -- `UnifiedMessage.voice_file_id` and `voice_duration` fields
- `src/channels/telegram.py` -- Voice message parsing, `download_file` via Bot API
- `src/channels/whatsapp.py` -- `download_file` raises `NotImplementedError` (post-MVP)
- `src/db/evidence.py` -- `voice_enrolled`, `voice_enroll_phrase_rejected`, `voice_verified` in `VALID_EVENT_TYPES`
- `src/config.py` -- Voice cloud settings (embedding endpoint, timeouts, thresholds)
- `src/api/rate_limit.py` -- `check_voice_rate_limit` (sliding-window, config-backed limits)
- `migrations/versions/001_initial_schema.py` -- Includes the voice-related `users` columns in the squashed baseline

## Specification

### Configuration (`src/config.py`)

| Setting | Default | Purpose |
|---------|---------|---------|
| `voice_embedding_endpoint_url` | `""` | Modal embedding endpoint URL |
| `voice_embedding_auth_token` | `""` | Optional auth token for Modal endpoint |
| `voice_embedding_timeout_seconds` | `30.0` | HTTP timeout for Modal embedding calls |
| `voice_transcription_timeout_seconds` | `20.0` | HTTP timeout for OpenAI transcription calls |
| `voice_cloud_max_retries` | `2` | Retry count on cloud API failures |
| `voice_embedding_similarity_high` | `0.45` | Unified embedding high threshold (same-speaker min ~0.57, cross-speaker max ~0.31) |
| `voice_embedding_similarity_delta` | `0.07` | Moderate = high - delta = 0.38 |
| `voice_transcription_score_standard` | `0.65` | Unified standard transcription threshold (relaxed from 0.70) |
| `voice_transcription_score_strict` | `0.75` | Unified strict transcription threshold (relaxed from 0.80) |
| `voice_enrollment_phrases_per_session` | `3` | Phrases required per enrollment |
| `voice_enrollment_max_phrase_failures` | `3` | Total phrase failures before blocking |
| `voice_enrollment_attempts_per_phrase` | `2` | Retries per individual phrase |
| `voice_session_duration_minutes` | `30` | Voice session TTL from last activity |
| `voice_verification_max_attempts` | `4` | Max verification attempts per session |
| `voice_verification_rate_limit_count` | `5` | Voice verification attempts per window |
| `voice_verification_rate_limit_window_seconds` | `3600` | Rate limit window (1 hour) |
| `voice_audio_min_duration_seconds` | `1` | Minimum audio length (relaxed from 2s) |
| `voice_audio_max_duration_seconds` | `10` | Maximum audio length (reduced from 15s) |
| `voice_encryption_key` | `""` | Fernet key for encrypting voice embeddings at rest |
| `voice_phrases_file` | `voice-phrases.json` | Path to external phrases JSON |

### User Model Columns (`src/models/user.py`)

| Column | Type | Purpose |
|--------|------|---------|
| `voice_enrolled_at` | `DateTime(tz)`, nullable | Timestamp of completed enrollment |
| `voice_verified_at` | `DateTime(tz)`, nullable | Timestamp of last verification (session timer base) |
| `voice_embedding` | `LargeBinary`, nullable | Averaged 192-dim ECAPA2 embedding (768 bytes, float32 packed) |
| `voice_model_version` | `String(128)`, nullable | Model identifier for embedding compatibility checks |

### EnrollmentAudio Model (`src/models/enrollment_audio.py`)

| Column | Type | Purpose |
|--------|------|---------|
| `id` | `Integer`, PK | Auto-increment ID |
| `user_id` | `UUID`, FK->users | Owner |
| `phrase_id` | `Integer` | Which phrase slot (0, 1, 2) |
| `audio_ogg` | `LargeBinary` | Raw OGG Opus audio (~15-25 KB each) |
| `duration_seconds` | `Float`, nullable | Audio duration |
| `created_at` | `DateTime(tz)` | When stored |

Computed properties on User:
- `is_voice_enrolled` -> `voice_enrolled_at is not None and voice_embedding is not None`
- `is_voice_session_active` -> `voice_verified_at` is within `voice_session_duration_minutes` of now

### Enrollment Flow (`src/voice/enrollment.py`)

1. **Language choice**: After account linking, `route_message` calls `_prompt_enrollment_language` which sets `bot_state = "choosing_voice_lang"` and shows a bilingual language picker (🇬🇧 English / 🇮🇷 فارسی). User picks language → locale is set → enrollment starts.
2. **Trigger**: `_start_voice_enrollment` is called after language choice, or when an unenrolled user sends a voice message directly.
3. **State**: Stored in `user.bot_state_data` as dict: `{enrollment, step, phrase_ids, collected_embeddings, collected_audio, attempt, failures, failed_phrase_ids, model_version}`
4. **Bot state**: `user.bot_state = "enrolling_voice"`
5. **Language switch**: All enrollment and verification messages include a 🌐 language switch button (`vlang_en`/`vlang_fa` callback). Pressing it changes locale and restarts enrollment with new phrases, or picks a new verification phrase in the new language.
6. **Per phrase**: User reads phrase -> audio downloaded via `BaseChannel.download_file` -> sent to cloud APIs (OpenAI transcription + Modal embedding in parallel) -> transcription score checked against unified **strict** threshold. Rejections logged as `voice_enroll_phrase_rejected`.
5. **Accept**: Embedding stored in state as base64; raw audio stored as base64 for model portability; advance to next phrase
6. **Retry**: Attempt counter incremented; if attempts >= `voice_enrollment_attempts_per_phrase`, phrase replaced with a new one
7. **Block**: If total failures >= `voice_enrollment_max_phrase_failures`, enrollment blocked; 24-hour cooldown
8. **Finalize**: After all phrases collected, `finalize_enrollment` averages embeddings, stores on user, persists `EnrollmentAudio` records, sets `voice_enrolled_at` and `voice_verified_at`, logs `voice_enrolled` evidence event

### Verification Flow (`src/voice/verification.py`)

1. **Trigger**: `route_message` voice gate detects `is_voice_enrolled and not is_voice_session_active`
2. **Prompt**: Random phrase selected via `pick_verification_phrase`; shown with cancel + language switch buttons
3. **Bot state**: `user.bot_state = "awaiting_voice"`
4. **Check**: Audio processed by cloud APIs (parallel) -> `cosine_similarity` against stored embedding + transcription score -> `voice_decision` applies dual-threshold matrix
5. **Return**: `verify_voice` returns `VerificationOutcome = tuple[VerificationResult, VerificationErrorReason | None]` where:
   - `VerificationResult`: `"accept"`, `"reject"`, `"audio_error"`, `"service_error"`
   - `VerificationErrorReason`: `"too_short"` | `"too_long"` (duration), `"V002"` | `"V003"` | `"V004"` (technical), `"voice_mismatch"` | `"transcript_mismatch"` | `"both_mismatch"` (rejection reason)
   - Duration errors → user-friendly message ("audio too short/long")
   - Technical errors → message with code ("Error processing audio. Code: V003")
   - Rejections → specific message per mismatch type + phrase to retry
6. **Accept**: `voice_verified_at` updated, `voice_verified` evidence logged, user proceeds
7. **Reject**: Specific mismatch message shown (voice/transcript/both), then new phrase prompted (re-verification)
8. **Rate limit**: `check_voice_rate_limit` (5 attempts/hour per user) checked before each attempt

### Decision Matrix (`src/voice/scoring.py: voice_decision`)

| Embedding Similarity | Transcription Score | Result |
|---------------------|---------------------|--------|
| >= `sim_high` | >= `trans_standard` | **accept** |
| >= `sim_moderate` | >= `trans_strict` | **accept** |
| Otherwise | -- | **reject** |

### Transcription Scoring (`src/voice/transcription_scoring.py`)

- **English**: `word_overlap_score` -- fraction of expected words that appear in the transcription (set overlap)
- **Farsi**: `farsi_phrase_score` -- per-word subsequence matching with homophone equivalence map (ت/ط, س/ص/ث, ز/ظ/ض/ذ, ق/غ, ح/ه)

### Evidence Logging

| Event | Payload (no biometric data) |
|-------|-----------------------------|
| `voice_enrolled` | `{phrases_used, model_version}` |
| `voice_enroll_phrase_rejected` | `{transcription_score, trans_strict, phrase_id, attempt}` |
| `voice_verified` | `{decision, embedding_similarity, transcription_score, phrase_id}` |

## Constraints

- Embeddings stored as `LargeBinary`, encrypted at rest via Fernet when `VOICE_ENCRYPTION_KEY` is configured; backward-compatible with unencrypted legacy data
- Evidence log entries contain only scores and phrase IDs -- never raw audio, embeddings, or biometric data
- All voice settings config-backed via `src/config.py`
- Enrollment audio stored in DB for model portability (~45-75 KB per user for 3 phrases)
- Phrase pools loaded from external JSON file (`voice-phrases.json`), gitignored and deployed as a secret
- Phrase selection uses `secrets.randbelow` for cryptographic randomness
- Rate limiting via in-process sliding-window counter (config-backed limits)

## Tests

| File | Coverage |
|------|----------|
| `tests/test_voice/test_scoring.py` | Cosine similarity, decision matrix, embedding serialization/deserialization, averaging |
| `tests/test_voice/test_phrases.py` | Phrase selection, exclusion, edge cases, `get_phrase` validation |
| `tests/test_voice/test_client.py` | `VoiceCloudClient`: success, parallel execution, error handling |
| `tests/test_voice/test_transcription.py` | OpenAI transcription client: success, retry, timeout |
| `tests/test_voice/test_embedding.py` | Modal embedding client: success, error, auth token |
| `tests/test_voice/test_transcription_scoring.py` | Word overlap (EN), subsequence+homophone (FA), edge cases |
| `tests/test_voice/test_enrollment.py` | State machine: init, phrase accept/retry/replace/block, finalize with audio storage |
| `tests/test_voice/test_verification.py` | Accept, reject, audio error, service error, evidence logging |
| `tests/test_handlers/test_commands_voice.py` | Voice gate integration: enrollment start, verification flow, session extension, rate limiting |
| `tests/test_channels/test_telegram_voice.py` | Voice message parsing, file download |

### Migration

- `migrations/versions/001_initial_schema.py` -- includes both the voice-related `users` columns and the `enrollment_audio` table in the squashed baseline
