"use client";

import Link from "next/link";
import {signOut} from "next-auth/react";
import {useLocale, useTranslations} from "next-intl";
import {usePathname} from "next/navigation";

import {LanguageSwitcher} from "./LanguageSwitcher";

type NavBarProps = {
  showOpsLink: boolean;
  userEmail?: string;
};

export function NavBar({showOpsLink, userEmail}: NavBarProps) {
  const t = useTranslations("nav");
  const common = useTranslations("common");
  const appTitle = common("appTitle");
  const locale = useLocale();
  const pathname = usePathname();

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
      {/* Top row: title + (desktop links) + user/lang */}
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        <Link
          href={`/${locale}`}
          className="shrink-0 text-lg font-bold tracking-tight text-gray-900 dark:text-white"
        >
          {appTitle}
        </Link>

        {/* Desktop nav links (hidden on mobile) */}
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
        </div>

        {/* Right group: telegram + user + language (always visible) */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          <a
            href="https://t.me/collective_will_dev_bot"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center rounded-full bg-[#2AABEE] p-1.5 text-white transition-opacity hover:opacity-80"
            title="Telegram"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71L12.6 16.3l-1.99 1.93c-.23.23-.42.42-.83.42z" />
            </svg>
          </a>
          {userEmail ? (
            <>
              <span className="hidden rounded-lg bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-700 dark:bg-slate-700 dark:text-slate-300 sm:inline">
                {userEmail}
              </span>
              <button
                type="button"
                onClick={() => signOut({callbackUrl: `/${locale}`})}
                className="rounded-md p-1.5 text-sm font-medium text-gray-500 transition-colors hover:bg-red-50 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                title={common("logout")}
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
                </svg>
              </button>
            </>
          ) : (
            <Link
              href={`/${locale}/sign-in`}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-accent-hover sm:px-4 sm:text-sm"
            >
              {common("login")}
            </Link>
          )}
          <div className="border-s border-gray-200 ps-1.5 dark:border-slate-700 sm:ps-3">
            <LanguageSwitcher />
          </div>
        </div>
      </div>

      {/* Mobile scrollable nav strip (hidden on desktop) */}
      <div className="scrollbar-hide flex overflow-x-auto border-t border-gray-100 px-4 dark:border-slate-800 md:hidden">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`shrink-0 border-b-2 px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors ${
              isActive(link.href)
                ? "border-accent text-accent dark:text-indigo-300"
                : "border-transparent text-gray-500 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white"
            }`}
          >
            {link.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
