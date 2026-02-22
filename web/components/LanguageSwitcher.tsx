"use client";

import {useRouter, usePathname} from "next/navigation";
import {useLocale} from "next-intl";

export function LanguageSwitcher() {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  const changeLocale = (value: string) => {
    const segments = pathname.split("/");
    segments[1] = value;
    router.push(segments.join("/"));
  };

  return (
    <div className="flex items-center gap-1 text-sm">
      <button
        type="button"
        onClick={() => changeLocale("en")}
        aria-label="English"
        className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
          locale === "en"
            ? "bg-accent/10 text-accent dark:text-indigo-300"
            : "text-gray-500 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white"
        }`}
      >
        EN
      </button>
      <span className="text-gray-300 dark:text-slate-600">/</span>
      <button
        type="button"
        onClick={() => changeLocale("fa")}
        aria-label="فارسی"
        className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
          locale === "fa"
            ? "bg-accent/10 text-accent dark:text-indigo-300"
            : "text-gray-500 hover:text-gray-900 dark:text-slate-400 dark:hover:text-white"
        }`}
      >
        FA
      </button>
    </div>
  );
}
