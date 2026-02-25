"use client";

import {useSearchParams, useRouter} from "next/navigation";
import {useCallback, useEffect, useState} from "react";
import {useTranslations, useLocale} from "next-intl";
import {signIn} from "next-auth/react";
import Link from "next/link";

import {apiPost} from "@/lib/api";
import {setUserEmailCookie} from "@/lib/user-session";
import {Card} from "@/components/ui";

export default function VerifyPage() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const t = useTranslations("verify");
  const signupT = useTranslations("signup");
  const locale = useLocale();
  const router = useRouter();
  const [status, setStatus] = useState<"verifying" | "success" | "error">("verifying");
  const [errorDetail, setErrorDetail] = useState<"expired" | "invalid">("invalid");
  const [linkingCode, setLinkingCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorDetail("invalid");
      return;
    }
    apiPost<{status: string; email?: string; web_session_code?: string}>(`/auth/verify/${token}`, {})
      .then(async (result) => {
        if (result.email) {
          setUserEmailCookie(result.email);
        }
        if (result.email && result.web_session_code) {
          const signInResult = await signIn("credentials", {
            email: result.email,
            webSessionCode: result.web_session_code,
            redirect: false,
          });
          if (signInResult?.ok) {
            router.refresh();
          }
        }
        if (result.status === "verified") {
          router.replace(`/${locale}`);
        } else {
          setStatus("success");
          if (result.status) {
            setLinkingCode(result.status);
          }
        }
      })
      .catch((err) => {
        setStatus("error");
        const message = err instanceof Error ? err.message : "";
        setErrorDetail(message.includes("expired") ? "expired" : "invalid");
      });
  }, [token, router]);

  const handleCopy = useCallback(() => {
    if (!linkingCode) return;
    navigator.clipboard.writeText(linkingCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [linkingCode]);

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        {/* Step indicator */}
        <div className="mb-8 flex items-center justify-center gap-3">
          <StepDot number={1} label={signupT("stepEmail")} completed={status === "success"} active={status === "verifying"} />
          <div className="h-px w-8 bg-gray-300 dark:bg-slate-600" />
          <StepDot number={2} label={signupT("stepTelegram")} completed={false} active={status === "success"} />
        </div>

        {status === "verifying" && (
          <Card className="text-center">
            <div className="py-8">
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-accent" />
              <p className="mt-4 text-sm text-gray-500 dark:text-slate-400">{t("verifying")}</p>
            </div>
          </Card>
        )}

        {status === "error" && (
          <Card className="text-center">
            <div className="py-8">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
                <svg className="h-7 w-7 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h1 className="mt-4 text-lg font-bold">{t("errorTitle")}</h1>
              <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
                {errorDetail === "expired" ? t("errorExpired") : t("errorInvalid")}
              </p>
              <Link
                href={`/${locale}/signup`}
                className="mt-6 inline-block rounded-lg bg-accent px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
              >
                {signupT("stepEmail")}
              </Link>
            </div>
          </Card>
        )}

        {status === "success" && (
          <Card>
            <div className="space-y-6 py-2">
              {/* Success header */}
              <div className="text-center">
                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
                  <svg className="h-7 w-7 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h1 className="mt-4 text-lg font-bold">{t("emailVerified")}</h1>
                <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">{t("nowConnectTelegram")}</p>
              </div>

              {linkingCode && (
                <>
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-slate-600 dark:bg-slate-700/50">
                    <p className="mb-3 text-center text-sm font-medium text-gray-700 dark:text-slate-300">
                      {t("linkingCodeInstruction")}
                    </p>
                    <div className="flex items-center justify-center gap-2">
                      <code className="rounded-lg bg-white px-5 py-2.5 font-mono text-xl font-bold tracking-wider text-gray-900 shadow-sm dark:bg-slate-800 dark:text-white">
                        {linkingCode}
                      </code>
                      <button
                        type="button"
                        onClick={handleCopy}
                        className="rounded-md p-2 text-gray-400 transition-colors hover:bg-gray-200 hover:text-gray-600 dark:hover:bg-slate-600 dark:hover:text-slate-200"
                        aria-label={t("copyCode")}
                      >
                        {copied ? (
                          <svg className="h-5 w-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0 0 13.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 0 1-.75.75H9.75a.75.75 0 0 1-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 0 1-2.25 2.25H6.75A2.25 2.25 0 0 1 4.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 0 1 1.927-.184" />
                          </svg>
                        )}
                      </button>
                    </div>
                    <p className="mt-2 text-center text-xs text-gray-400 dark:text-slate-500">{t("codeExpiry")}</p>
                  </div>

                  {/* Telegram bot button */}
                  <a
                    href="https://t.me/collective_will_dev_bot"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#2AABEE] px-6 py-3 text-sm font-semibold text-white shadow-md transition-colors hover:bg-[#229ED9]"
                  >
                    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
                    </svg>
                    {t("openBot")}
                  </a>
                </>
              )}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function StepDot({number, label, active, completed}: {number: number; label: string; active: boolean; completed: boolean}) {
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
