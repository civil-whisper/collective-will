"use client";

import {FormEvent, useState} from "react";
import {useTranslations, useLocale} from "next-intl";

import {apiPost} from "@/lib/api";

export function SubscribeForm() {
  const t = useTranslations("landing");
  const common = useTranslations("common");
  const locale = useLocale();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus("loading");
    try {
      await apiPost("/auth/subscribe", {
        email,
        locale,
        requester_ip: "127.0.0.1",
        messaging_account_ref: `web-${crypto.randomUUID()}`,
      });
      setStatus("success");
    } catch {
      setStatus("error");
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
      <input
        type="email"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder={t("emailPlaceholder")}
        aria-label={t("emailPlaceholder")}
        className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-gray-400 focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-slate-600 dark:bg-slate-800 dark:placeholder:text-slate-500 sm:w-72"
      />
      <button
        type="submit"
        disabled={status === "loading"}
        className="w-full rounded-lg bg-accent px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-50 sm:w-auto"
      >
        {status === "loading" ? common("loading") : t("subscribeCta")}
      </button>
      {status === "success" && (
        <p role="status" className="text-sm font-medium text-green-600 dark:text-green-400">
          {t("successMessage")}
        </p>
      )}
      {status === "error" && (
        <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
          {t("errorMessage")}
        </p>
      )}
    </form>
  );
}
