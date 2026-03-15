"use client";

import Link from "next/link";
import {useTranslations, useLocale} from "next-intl";

export function Footer() {
  const t = useTranslations("footer");
  const locale = useLocale();

  return (
    <footer className="mt-16 border-t border-gray-200 dark:border-slate-700">
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between">
          <div className="text-center sm:text-start">
            <p className="text-sm font-semibold text-gray-900 dark:text-white">
              {t("copyright")}
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-slate-400">
              {t("tagline")}
            </p>
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-slate-400">
            <a href="https://t.me/collective_will_dev_bot" target="_blank" rel="noopener noreferrer" className="transition-colors hover:text-gray-900 dark:hover:text-white">
              {t("telegram")}
            </a>
            <a href="https://github.com/civil-whisper/collective-will" target="_blank" rel="noopener noreferrer" className="transition-colors hover:text-gray-900 dark:hover:text-white">
              {t("source")}
            </a>
            <Link
              href={`/${locale}/independent-verification`}
              className="transition-colors hover:text-gray-900 dark:hover:text-white"
            >
              {t("verify")}
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
