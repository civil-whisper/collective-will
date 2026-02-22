"use client";

import {useRouter, usePathname} from "next/navigation";
import {useLocale, useTranslations} from "next-intl";

export function LanguageSwitcher() {
  const t = useTranslations("common");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  const changeLocale = (value: string) => {
    const segments = pathname.split("/");
    segments[1] = value;
    router.push(segments.join("/"));
  };

  return (
    <label>
      {t("language")}{" "}
      <select
        aria-label={t("language")}
        value={locale}
        onChange={(event) => changeLocale(event.target.value)}
      >
        <option value="fa">فارسی</option>
        <option value="en">English</option>
      </select>
    </label>
  );
}
