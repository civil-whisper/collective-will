# Task: Next.js Setup with i18n

## Depends on
Nothing — this is the first website task. The Python backend should be running (database module complete) but is not required for initial setup.

## Goal
Create the Next.js App Router project with Tailwind CSS, Farsi RTL support, English as secondary locale, and a basic layout shell.

## Files to create

- `web/package.json`
- `web/tsconfig.json`
- `web/tailwind.config.ts`
- `web/postcss.config.js`
- `web/next.config.ts` — with next-intl config
- `web/middleware.ts` — locale detection and routing
- `web/messages/fa.json` — Farsi translations
- `web/messages/en.json` — English translations
- `web/app/[locale]/layout.tsx` — root layout with RTL/LTR support
- `web/app/[locale]/page.tsx` — placeholder home page
- `web/components/LanguageSwitcher.tsx`
- `web/components/NavBar.tsx`

## Specification

### Project setup

Initialize with:
```bash
pnpm create next-app web --typescript --tailwind --app --src-dir=false
```

Then add dependencies:
```bash
pnpm add next-intl
```

### next-intl configuration

Locales: `["fa", "en"]`, default: `"fa"`

`web/middleware.ts`:
```typescript
import createMiddleware from "next-intl/middleware";

export default createMiddleware({
  locales: ["fa", "en"],
  defaultLocale: "fa",
});

export const config = {
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
```

### RTL support

The root layout must set `dir` and `lang` based on locale:

```typescript
// app/[locale]/layout.tsx
export default function RootLayout({ children, params: { locale } }) {
  const dir = locale === "fa" ? "rtl" : "ltr";
  return (
    <html lang={locale} dir={dir}>
      <body>{children}</body>
    </html>
  );
}
```

### Tailwind RTL

Add RTL utilities to Tailwind config. Use the `rtl:` variant or CSS logical properties (`ms-`, `me-`, `ps-`, `pe-` instead of `ml-`, `mr-`, `pl-`, `pr-`).

### Translation files

`messages/fa.json`:
```json
{
  "nav": {
    "home": "خانه",
    "analytics": "تحلیل‌ها",
    "dashboard": "داشبورد",
    "about": "درباره ما",
    "audit": "بررسی شواهد"
  },
  "common": {
    "loading": "در حال بارگذاری...",
    "error": "خطایی رخ داد",
    "login": "ورود",
    "logout": "خروج"
  }
}
```

`messages/en.json`:
```json
{
  "nav": {
    "home": "Home",
    "analytics": "Analytics",
    "dashboard": "Dashboard",
    "about": "About",
    "audit": "Audit"
  },
  "common": {
    "loading": "Loading...",
    "error": "An error occurred",
    "login": "Sign In",
    "logout": "Sign Out"
  }
}
```

### NavBar

Simple navigation bar with links to: Home, Analytics, Dashboard, About, Audit. Include the LanguageSwitcher component. Responsive (hamburger menu on mobile).

### LanguageSwitcher

A button/dropdown that switches between Farsi and English. Uses next-intl's `useRouter` and `usePathname` to preserve the current path when switching locale.

## Constraints

- Farsi is the PRIMARY locale. Default to Farsi, not English.
- All text in components must use `useTranslations()` from next-intl. No hardcoded strings.
- Use CSS logical properties for spacing/alignment so RTL works without separate stylesheets.
- Do NOT add authentication yet (that's task 03).

## Tests

Write tests in `web/__tests__/` (or `web/app/__tests__/`) covering:
- App builds without errors (`pnpm build`)
- Home page renders for `/fa` (Farsi locale)
- Home page renders for `/en` (English locale)
- Farsi page has `dir="rtl"` and `lang="fa"` on html element
- English page has `dir="ltr"` and `lang="en"`
- NavBar renders all navigation links
- LanguageSwitcher is present and functional (clicking switches locale)

Use vitest or jest with React Testing Library.
