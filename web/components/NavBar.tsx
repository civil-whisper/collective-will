"use client";

import Link from "next/link";
import {useLocale, useTranslations} from "next-intl";
import {usePathname} from "next/navigation";
import {useState} from "react";

import {LanguageSwitcher} from "./LanguageSwitcher";

export function NavBar() {
  const t = useTranslations("nav");
  const common = useTranslations("common");
  const appTitle = common("appTitle");
  const locale = useLocale();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const showOpsLink = process.env.NEXT_PUBLIC_OPS_CONSOLE_SHOW_IN_NAV === "true";

  const links = [
    {href: `/${locale}`, label: t("home")},
    {href: `/${locale}/analytics`, label: t("analytics")},
    {href: `/${locale}/analytics/top-policies`, label: t("topPolicies")},
    {href: `/${locale}/dashboard`, label: t("dashboard")},
    {href: `/${locale}/analytics/evidence`, label: t("audit")},
    ...(showOpsLink ? [{href: `/${locale}/ops`, label: t("ops")}] : []),
  ];

  const isActive = (href: string) => pathname === href;

  return (
    <nav
      role="navigation"
      aria-label="Main navigation"
      className="sticky top-0 z-50 border-b border-gray-200 bg-white/80 backdrop-blur-md dark:border-slate-700 dark:bg-slate-900/80"
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        <Link
          href={`/${locale}`}
          className="text-lg font-bold tracking-tight text-gray-900 dark:text-white"
        >
          {appTitle}
        </Link>

        {/* Desktop links */}
        <div className="hidden items-center gap-1 md:flex">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                isActive(link.href)
                  ? "bg-accent/10 text-accent dark:text-indigo-300"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <Link
            href={`/${locale}/signup`}
            className="ms-2 rounded-lg bg-accent px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
          >
            {common("signup")}
          </Link>
          <div className="ms-3 border-s border-gray-200 ps-3 dark:border-slate-700">
            <LanguageSwitcher />
          </div>
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="Toggle menu"
          aria-expanded={menuOpen}
          className="inline-flex items-center justify-center rounded-md p-2 text-gray-600 hover:bg-gray-100 dark:text-slate-300 dark:hover:bg-slate-800 md:hidden"
        >
          {menuOpen ? (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="border-t border-gray-200 bg-white px-4 pb-4 pt-2 dark:border-slate-700 dark:bg-slate-900 md:hidden">
          <div className="space-y-1">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className={`block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  isActive(link.href)
                    ? "bg-accent/10 text-accent dark:text-indigo-300"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-slate-300 dark:hover:bg-slate-800"
                }`}
              >
                {link.label}
              </Link>
            ))}
          </div>
          <Link
            href={`/${locale}/signup`}
            onClick={() => setMenuOpen(false)}
            className="mt-2 block rounded-lg bg-accent px-4 py-2 text-center text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
          >
            {common("signup")}
          </Link>
          <div className="mt-3 border-t border-gray-200 pt-3 dark:border-slate-700">
            <LanguageSwitcher />
          </div>
        </div>
      )}
    </nav>
  );
}
