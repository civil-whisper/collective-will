# Task: Identity Verification

## Depends on
- `messaging/03-webhook-endpoint` (FastAPI app and routes)
- `messaging/02-whatsapp-evolution-client` (opaque account ref mapping)
- `database/03-core-models` (User model, CRUD queries)
- `database/04-evidence-store` (append_evidence)

## Goal
Implement the full identity verification flow: email magic-link signup, token verification, and messaging account linking (Telegram for MVP, WhatsApp post-MVP).

## Files to create/modify

- `src/handlers/identity.py` — identity/verification logic
- `src/api/routes/auth.py` — auth API endpoints
- `src/api/main.py` — register auth router

## Specification

### POST /api/auth/subscribe

Input: `{"email": "user@example.com"}`

Steps:
1. Validate email format
2. Check if email already registered. If so, send a new magic link (re-verify flow).
3. Check per-IP signup cap: block if requester IP exceeded `MAX_SIGNUPS_PER_IP_PER_DAY` in last 24h
4. Determine if domain is major provider (`MAJOR_EMAIL_PROVIDERS`)
5. If domain is non-major, enforce domain cap `MAX_SIGNUPS_PER_DOMAIN_PER_DAY` (default 3/day)
6. Track signup anomaly telemetry: count distinct email domains requested from the same requester IP in the last 24h; if anomalous, flag for review/monitoring
7. Detect disposable-email domains and record as a negative `trust_score` signal (soft signal only, do not auto-reject by itself)
8. Generate magic-link token using `secrets.token_urlsafe(32)`
9. Store token with expiry (15 minutes) — can use a `verification_tokens` table or store on user record
10. Send email with magic link: `{settings.app_public_base_url}/verify?token={token}` (production: `https://collectivewill.org`)
11. If user doesn't exist yet, create User record with `email_verified=False`
12. Log account-creation velocity metrics (per IP, per domain, global) for abuse monitoring dashboards
13. Return `{"status": "magic_link_sent"}`

Email sending uses Resend (REST API via httpx). When `RESEND_API_KEY` is set, real emails are delivered; otherwise magic links are logged to console (dev mode). The sender module is at `src/email/sender.py` with bilingual HTML templates (Farsi/English based on locale).

### GET /api/auth/verify

Query param: `token`

Steps:
1. Look up token
2. If token doesn't exist or is expired → return 400
3. If token is valid → set `email_verified=True` on the user
4. Log `user_verified` event to evidence store
5. Delete/invalidate the token
6. Return success page/redirect with instructions to connect WhatsApp

### Failed attempt tracking

- Track failed verification attempts per email (IP-based tracking is optional for v0)
- After 5 failed attempts in 24 hours → 24-hour lockout on that email
- Return generic error (don't reveal whether email exists)

### Messaging account linking

When a verified user sends their linking code to the Telegram bot (MVP) or WhatsApp bot (post-MVP):

The backend provides two paths:

1. **`resolve_linking_code(code, account_ref)`** — generic, used by any channel. Looks up the linking code, finds the associated email/user, sets `messaging_account_ref` and `messaging_verified`.
2. **`link_whatsapp_account(user, account_ref)`** — direct linking for WhatsApp (post-MVP).

Steps:
1. If the user already has `messaging_verified=True` → reject with `user_already_linked` (prevents re-linking to a different messaging account)
2. Check that no other user is already linked to this `account_ref` → reject with `account_already_linked` (enforces one-Telegram-one-user, providing implicit phone-number uniqueness for Sybil resistance)
3. Set `user.messaging_account_ref = account_ref` (opaque UUIDv4, never raw platform ID)
4. Set `user.messaging_verified = True`
5. Set `user.messaging_account_age` to current time
6. Log `user_verified` event (type: `messaging_linked`) to evidence store

The bot (`route_message` in `src/handlers/commands.py`) surfaces both rejection cases with Farsi user-facing messages explaining the conflict.

### Linking code

- Generated after email verification: `secrets.token_urlsafe(8)` (short, easy to type)
- Stored in `verification_tokens` DB table with 1-hour expiry
- User receives the code on the `/verify` page after clicking the magic link
- Website shows the code prominently with a copy button and "Open Telegram Bot" deep link
- User sends this code as a message to the bot
- Bot calls `resolve_linking_code` → links account

## Constraints

- Use `secrets` module for all token generation. NEVER use `random`.
- Do NOT store raw WhatsApp IDs. Store only opaque account refs in core tables.
- Magic link tokens must expire (15 minutes). Linking codes must expire (1 hour).
- Generic error responses — do not reveal whether an email is registered.
- Email sending is a stub for now (print/log the link). Do not add email service dependencies.
- Build absolute links using `APP_PUBLIC_BASE_URL`; do not hardcode hostnames in auth flows.
- Disposable-email detection is a soft trust signal in v0, not a hard rejection rule.
- Per-IP signup cap is a hard block for abuse control in v0.
- Domain cap applies only to non-major domains; major providers are exempt.

## Tests

Write tests in `tests/test_handlers/test_identity.py` and `tests/test_api/test_auth.py` covering:
- `POST /api/auth/subscribe` with valid email returns 200
- `POST /api/auth/subscribe` with invalid email returns 422
- `POST /api/auth/subscribe` creates user with `email_verified=False`
- Domain rate limit: 4th account on non-major domain blocked
- Major provider exemption: 4th signup on major domain is not blocked by domain cap
- Per-IP signup cap: request over configured cap returns rate-limit response
- Signup anomaly telemetry: high distinct-domain count from one IP gets flagged (without blocking)
- Disposable-email domain updates `trust_score` signal and still returns success path in v0
- `GET /api/auth/verify` with valid token sets `email_verified=True`
- `GET /api/auth/verify` with expired token returns 400
- `GET /api/auth/verify` with invalid token returns 400
- Lockout after 5 failed verification attempts (returns 429)
- WhatsApp linking: valid linking code sets `messaging_verified=True`
- WhatsApp linking: expired code rejected
- WhatsApp linking: code already used rejected
- WhatsApp linking stores opaque account ref, not raw ID
- Linking rejected when user already has a linked messaging account (`user_already_linked`)
- Linking rejected when messaging account is already linked to another user (`account_already_linked`)
- Evidence logged for both email verification and WhatsApp linking
- Account-creation velocity metrics are emitted on subscribe attempts
