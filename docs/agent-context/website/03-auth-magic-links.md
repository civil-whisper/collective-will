# Task: Authentication with Magic Links

## Depends on
- `website/01-nextjs-setup-i18n` (Next.js project)

## Goal
Set up NextAuth.js with email magic link authentication. Users log in by clicking a link sent to their email — no passwords.

## Files to create/modify

- `web/app/api/auth/[...nextauth]/route.ts` — NextAuth.js route handler
- `web/lib/auth.ts` — auth configuration
- `web/components/AuthProvider.tsx` — session provider wrapper
- `web/app/[locale]/layout.tsx` — wrap with AuthProvider
- `web/lib/auth-guard.tsx` — protected route HOC or hook
- `web/app/[locale]/verify/page.tsx` — verification landing page

## Specification

### NextAuth.js configuration

```typescript
// web/lib/auth.ts
import NextAuth from "next-auth";
import EmailProvider from "next-auth/providers/email";

export const authOptions = {
  providers: [
    EmailProvider({
      server: process.env.EMAIL_SERVER,  // SMTP or stub
      from: process.env.EMAIL_FROM,
    }),
  ],
  // Use the Python backend as the source of truth for user data
  // NextAuth manages sessions; user records live in Postgres via Python backend
  callbacks: {
    async signIn({ user, email }) {
      // Call Python backend to verify/create user
      return true;
    },
    async session({ session, token }) {
      // Attach user ID from backend to session
      return session;
    },
  },
};
```

For v0, email sending can use a stub/console adapter (log the magic link URL instead of sending email). This allows development without an SMTP server.

### Signup page

`/signup` — dedicated two-step signup flow (implemented).

- Step 1: Email input form → calls `POST /auth/subscribe` → shows "check your email" confirmation
- Step 2: Handled by `/verify` after magic link click → shows linking code + Telegram bot link
- Visual step indicator tracks progress (1. Verify Email, 2. Connect Telegram)
- Info blurbs explain why email and Telegram are needed, no phone numbers collected
- Rate limit (429) and generic error states handled
- Links to sign-in for existing users

### Verification page

`/verify?token=...` — the page users land on after clicking the magic link (implemented).

- Shows "Verifying..." while the backend processes the token
- On success: shows linking code with copy button + "Open Telegram Bot" deep link + 60-min expiry notice
- On failure: distinguishes expired vs invalid tokens, links back to `/signup`
- Same step indicator showing email completed, Telegram active

### Protected routes

Create a utility to protect dashboard routes:

```typescript
// web/lib/auth-guard.tsx
export function withAuth(Component) {
  // If not authenticated, redirect to sign-in
  // If authenticated, render component with session data
}
```

Or use middleware to protect `/dashboard/*` routes.

Routes that require auth:
- `/dashboard`
- `/dashboard/submissions`
- `/dashboard/votes`

Routes that are public (no auth):
- `/` (landing)
- `/analytics` and sub-pages
- `/about`
- `/audit`

### Session management

- Sessions stored as JWT (default NextAuth behavior)
- Session duration: 30 days
- No refresh token rotation needed for v0

### Environment variables

Add to `web/.env.local` (and `.env.example`):
```
NEXTAUTH_SECRET=random_secret_min_32_chars
NEXTAUTH_URL=http://localhost:3000
EMAIL_SERVER=smtp://user:pass@smtp.example.com:587  # or stub
EMAIL_FROM=noreply@collectivewill.org
BACKEND_URL=http://localhost:8000
```

## Constraints

- No passwords. Magic links only.
- NextAuth handles session management. User records and verification state live in the Python backend's database.
- The auth flow must work with both Farsi and English locales.
- Do NOT store sensitive user data in the JWT. Only session ID and basic info (email, locale).
- Email sending is a stub for development. Do not require a real SMTP server to run locally.

## Tests

Write tests covering:
- NextAuth configuration loads without errors
- Email provider is configured
- Unauthenticated user accessing `/dashboard` is redirected to sign-in
- Authenticated user can access `/dashboard`
- `/analytics` is accessible without auth
- `/verify` page renders
- Session contains expected user fields (email, locale)
- AuthProvider wraps the app correctly
- Protected route HOC/hook redirects unauthenticated users
