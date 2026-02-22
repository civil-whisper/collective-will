"use client";

import Link from "next/link";
import {useLocale, useTranslations} from "next-intl";
import {useState} from "react";

import {LanguageSwitcher} from "./LanguageSwitcher";

export function NavBar() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const [menuOpen, setMenuOpen] = useState(false);

  const links = [
    {href: `/${locale}`, label: t("home")},
    {href: `/${locale}/analytics`, label: t("analytics")},
    {href: `/${locale}/analytics/top-policies`, label: t("topPolicies")},
    {href: `/${locale}/dashboard`, label: t("dashboard")},
    {href: `/${locale}/analytics/evidence`, label: t("audit")},
  ];

  return (
    <nav role="navigation" aria-label="Main navigation">
      <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1rem"}}>
        <Link href={`/${locale}`} style={{fontWeight: "bold", fontSize: "1.2rem"}}>
          {t("home")}
        </Link>
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          aria-label="Toggle menu"
          aria-expanded={menuOpen}
          style={{display: "none"}}
          className="mobile-menu-toggle"
        >
          ☰
        </button>
        <div style={{display: "flex", gap: "1rem", alignItems: "center"}}>
          {links.map((link) => (
            <Link key={link.href} href={link.href}>
              {link.label}
            </Link>
          ))}
          <LanguageSwitcher />
        </div>
      </div>
      {menuOpen && (
        <div className="mobile-menu" style={{padding: "1rem"}}>
          {links.map((link) => (
            <div key={link.href} style={{padding: "0.5rem 0"}}>
              <Link href={link.href} onClick={() => setMenuOpen(false)}>
                {link.label}
              </Link>
            </div>
          ))}
          <LanguageSwitcher />
        </div>
      )}
    </nav>
  );
}
