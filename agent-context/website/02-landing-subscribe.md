# Task: Landing Page and Subscribe Form

## Depends on
- `website/01-nextjs-setup-i18n` (Next.js project with i18n)

## Goal
Create the landing page with the project's value proposition and an email subscribe form that starts the registration flow.

## Files to create/modify

- `web/app/[locale]/page.tsx` — landing page (replace placeholder)
- `web/components/SubscribeForm.tsx` — email subscribe form
- `web/components/HeroSection.tsx` — hero section
- `web/messages/fa.json` — add landing page translations
- `web/messages/en.json` — add landing page translations

## Specification

### Landing page sections

1. **Hero section**: Large headline + subtitle + subscribe CTA
   - Farsi: `"ایرانیان چه می‌خواهند؟ به ما کمک کنید تا بفهمیم."`
   - English: `"What do Iranians want? Help us find out."`
   - Subtitle explaining: submit concerns, AI organizes, community votes, everything transparent

2. **How it works**: 3-4 step visual (icons + short text)
   - Step 1: Submit your concern via WhatsApp
   - Step 2: AI organizes without editorializing
   - Step 3: Community votes on priorities
   - Step 4: Results are public and auditable

3. **Subscribe CTA**: Email input + button (repeated from hero)

4. **Trust section**: Brief explanation of transparency
   - "Everything is auditable. Every step is logged."
   - Link to /audit page

### SubscribeForm component

```typescript
interface SubscribeFormProps {
  className?: string;
}
```

- Email input with validation (client-side: valid email format)
- Submit button
- States: idle, loading, success, error
- On submit: POST to `/api/auth/subscribe` with `{ email }`
- Success message: "لینک تأیید ارسال شد! ایمیل خود را بررسی کنید." / "Verification link sent! Check your email."
- Error message: show server error or generic "Something went wrong"

### API proxy

The subscribe form calls the Python backend. Set up a Next.js API route or configure `next.config.ts` to proxy `/api/*` to the Python backend at `http://backend:8000` (or the configured API URL).

```typescript
// next.config.ts
async rewrites() {
  return [
    {
      source: "/api/:path*",
      destination: `${process.env.BACKEND_URL}/api/:path*`,
    },
  ];
}
```

Add `BACKEND_URL` to the environment config.

### Design

- Clean, modern, minimal design
- Farsi typography: use a good Farsi-friendly font (e.g., Vazirmatn via Google Fonts or local)
- Large readable text for hero section
- Responsive: works on mobile and desktop
- Accessible: proper ARIA labels, keyboard navigation

## Constraints

- All text through i18n — no hardcoded strings.
- The form does NOT create a user account directly. It calls the Python backend's subscribe endpoint.
- Do NOT implement the actual email sending. The backend handles that (and stubs it in v0).
- The page must be fully functional without JavaScript for the initial render (SSR).

## Tests

Write tests covering:
- Landing page renders hero section with correct text (Farsi and English)
- Subscribe form renders with email input and submit button
- Form validates email format (rejects "notanemail", accepts "user@example.com")
- Form shows loading state during submission
- Form shows success message after successful API call (mock fetch)
- Form shows error message on API failure (mock fetch returning error)
- "How it works" section renders all steps
- Page is responsive (no horizontal overflow on narrow viewport)
