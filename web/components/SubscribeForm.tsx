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
        messaging_account_ref: "web-signup",
      });
      setStatus("success");
    } catch {
      setStatus("error");
    }
  };

  return (
    <form onSubmit={submit} style={{display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center"}}>
      <input
        type="email"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder={t("emailPlaceholder")}
        aria-label={t("emailPlaceholder")}
        style={{padding: "0.5rem 1rem", fontSize: "1rem"}}
      />
      <button type="submit" disabled={status === "loading"} style={{padding: "0.5rem 1.5rem", fontSize: "1rem"}}>
        {status === "loading" ? common("loading") : t("subscribeCta")}
      </button>
      {status === "success" && <p role="status">{t("successMessage")}</p>}
      {status === "error" && <p role="alert">{t("errorMessage")}</p>}
    </form>
  );
}
