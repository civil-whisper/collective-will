"use client";

import {FormEvent, useState} from "react";
import {useTranslations, useLocale} from "next-intl";
import Link from "next/link";

import {apiPost} from "@/lib/api";
import {Card} from "@/components/ui";

type Step = "email" | "sent";

export default function SignupPage() {
  const t = useTranslations("signup");
  const verify = useTranslations("verify");
  const locale = useLocale();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "rate_limited">("idle");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus("loading");
    try {
      await apiPost("/auth/subscribe", {
        email,
        locale,
        messaging_account_ref: `web-${crypto.randomUUID()}`,
      });
      setStatus("idle");
      setStep("sent");
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      setStatus(message.includes("429") ? "rate_limited" : "error");
    }
  };

  const handleResend = () => {
    setStep("email");
    setStatus("idle");
  };

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Step indicator */}
        <div className="mb-8 flex items-center justify-center gap-3">
          <StepIndicator number={1} label={t("stepEmail")} active={step === "email"} completed={step === "sent"} />
          <div className="h-px w-8 bg-gray-300 dark:bg-slate-600" />
          <StepIndicator number={2} label={t("stepTelegram")} active={false} completed={false} />
        </div>

        {/* Header */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("title")}</h1>
          <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">{t("subtitle")}</p>
        </div>

        {step === "email" && (
          <Card className="space-y-5">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="signup-email" className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-slate-300">
                  {t("emailLabel")}
                </label>
                <input
                  id="signup-email"
                  type="email"
                  required
                  autoFocus
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t("emailPlaceholder")}
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-gray-400 focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-slate-600 dark:bg-slate-700 dark:placeholder:text-slate-500"
                />
              </div>
              <button
                type="submit"
                disabled={status === "loading"}
                className="w-full rounded-lg bg-accent px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
              >
                {status === "loading" ? t("emailSending") : t("emailSubmit")}
              </button>
            </form>

            {status === "error" && (
              <p role="alert" className="text-center text-sm font-medium text-red-600 dark:text-red-400">
                {t("emailError")}
              </p>
            )}
            {status === "rate_limited" && (
              <p role="alert" className="text-center text-sm font-medium text-red-600 dark:text-red-400">
                {t("rateLimited")}
              </p>
            )}

            {/* Info blurbs */}
            <div className="space-y-3 border-t border-gray-100 pt-4 dark:border-slate-700">
              <InfoRow
                icon={
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
                  </svg>
                }
                text={t("whyEmail")}
              />
              <InfoRow
                icon={
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
                  </svg>
                }
                text={t("whyTelegram")}
              />
            </div>

            <div className="text-center text-sm text-gray-500 dark:text-slate-400">
              {verify("alreadyHaveAccount")}{" "}
              <Link href={`/${locale}/sign-in`} className="font-medium text-accent hover:underline">
                {verify("signIn")}
              </Link>
            </div>
          </Card>
        )}

        {step === "sent" && (
          <Card className="text-center">
            <div className="py-4">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-accent/10">
                <svg className="h-7 w-7 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
                </svg>
              </div>
              <h2 className="mt-4 text-lg font-bold">{t("emailSent")}</h2>
              <p className="mt-2 text-sm text-gray-600 dark:text-slate-400">
                {t("emailSentDescription", {email})}
              </p>
              <p className="mt-4 text-xs text-gray-400 dark:text-slate-500">
                {t("emailSentTip")}{" "}
                <button
                  type="button"
                  onClick={handleResend}
                  className="font-medium text-accent hover:underline"
                >
                  {t("emailResend")}
                </button>
              </p>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function StepIndicator({number, label, active, completed}: {number: number; label: string; active: boolean; completed: boolean}) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold transition-colors ${
          completed
            ? "bg-green-500 text-white"
            : active
              ? "bg-accent text-white"
              : "bg-gray-200 text-gray-500 dark:bg-slate-700 dark:text-slate-400"
        }`}
      >
        {completed ? (
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        ) : (
          number
        )}
      </div>
      <span className={`text-xs font-medium ${active || completed ? "text-gray-900 dark:text-white" : "text-gray-400 dark:text-slate-500"}`}>
        {label}
      </span>
    </div>
  );
}

function InfoRow({icon, text}: {icon: React.ReactNode; text: string}) {
  return (
    <div className="flex items-start gap-2.5 text-xs text-gray-500 dark:text-slate-400">
      <div className="mt-0.5 shrink-0 text-gray-400 dark:text-slate-500">{icon}</div>
      <span>{text}</span>
    </div>
  );
}
