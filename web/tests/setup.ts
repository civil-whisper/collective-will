import "@testing-library/jest-dom/vitest";
import {vi} from "vitest";

import en from "../messages/en.json";

function lookupNamespace(obj: Record<string, unknown>, namespace: string): unknown {
  const parts = namespace.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current && typeof current === "object" && part in (current as Record<string, unknown>)) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}

function makeTranslator(namespace?: string) {
  const section = namespace ? lookupNamespace(en, namespace) : en;
  const t = (key: string) => {
    if (section && typeof section === "object") {
      return (section as Record<string, string>)[key] ?? `${namespace}.${key}`;
    }
    return `${namespace}.${key}`;
  };
  return t;
}

vi.mock("next-intl", () => ({
  useTranslations: makeTranslator,
  useLocale: () => "en",
  NextIntlClientProvider: ({children}: {children: React.ReactNode}) => children,
}));

vi.mock("next-intl/server", () => ({
  getTranslations: async (namespace?: string) => makeTranslator(namespace),
  getLocale: async () => "en",
  getMessages: async () => en,
}));

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({push: mockPush, replace: vi.fn(), back: vi.fn()}),
  usePathname: () => "/en/analytics",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (name === "cw_user_email" ? {value: "test@example.com"} : undefined),
  }),
}));

vi.mock("next/link", () => ({
  default: ({href, children, ...rest}: {href: string; children: React.ReactNode; [key: string]: unknown}) => {
    const React = require("react");
    return React.createElement("a", {href, ...rest}, children);
  },
}));

export {mockPush};
