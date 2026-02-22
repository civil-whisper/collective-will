# Task: Landing Page and Signup Flow

## Status: Implemented

## Depends on
- `website/01-nextjs-setup-i18n` (Next.js project with i18n)

## Goal
Landing page with the project's value proposition and clear CTAs to join. A dedicated two-step `/signup` page guides users through email verification and Telegram account linking.

## Implemented files

- `web/app/[locale]/page.tsx` — landing page with hero, "Join Now" + "Start Bot" CTAs, how-it-works grid, trust section
- `web/app/[locale]/signup/page.tsx` — two-step signup page (email → Telegram linking)
- `web/app/[locale]/verify/page.tsx` — email verification + linking code display with Telegram bot deep link
- `web/components/SubscribeForm.tsx` — legacy email subscribe form (still exists, no longer primary entry point)
- `web/components/NavBar.tsx` — includes "Sign Up" button linking to `/signup`
- `web/messages/fa.json` — `landing.*`, `signup.*`, `verify.*` namespaces
- `web/messages/en.json` — `landing.*`, `signup.*`, `verify.*` namespaces

## Current behavior

### Landing page (`/`)

1. **Hero section**: Headline + subtitle + two CTAs side by side:
   - "Join Now" — links to `/signup`
   - "Start the Bot on Telegram" — deep link to `t.me/collective_will_dev_bot`

2. **How it works**: 4-step icon grid
   - Step 1: Submit your concern via Telegram
   - Step 2: AI organizes without editorializing
   - Step 3: Community votes on priorities
   - Step 4: Results are public and auditable

3. **Trust section**: "Everything is auditable" with link to evidence page

### Signup page (`/signup`)

Two-step guided flow with visual step indicator (1. Verify Email, 2. Connect Telegram):

- **Step 1 (email)**: Email input form → calls `POST /auth/subscribe` → shows "Check your email" confirmation with resend option
- **Step 2 (Telegram)**: Handled by `/verify` page after magic link click
- Info blurbs explain why email (verification only) and Telegram (submit + vote)
- Links to sign-in for existing users
- Rate limit (429) and generic error states handled

### Verify page (`/verify?token=...`)

- Shows same step indicator with email completed, Telegram active
- On success: displays linking code with copy button + "Open Telegram Bot" deep link + expiry notice
- On error: distinguishes expired vs invalid tokens, links back to `/signup`

### NavBar

- "Sign Up" button in both desktop and mobile nav, linking to `/signup`

## Constraints

- All text through i18n — no hardcoded strings
- No phone numbers collected (frozen decision: no phone verification)
- The signup form calls the Python backend's subscribe endpoint; does not create accounts directly
- Email sending is stubbed in v0 (magic link logged to console)

## Tests

- `tests/signup-page.test.tsx` (11 tests): form rendering, submit flow, error/rate-limit states, resend, sign-in link
- `tests/verify-page.test.tsx` (10 tests): token states, linking code display, Telegram bot link, step indicators, error recovery
- `tests/navbar.test.tsx` (9 tests): includes signup link/button assertions
- `tests/messages.test.ts` (8 tests): includes signup/verify key parity checks
- `tests/subscribe-form.test.tsx` (5 tests): legacy form still tested
