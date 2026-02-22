"use client";

import {useSearchParams} from "next/navigation";
import {useEffect, useState} from "react";
import {useTranslations} from "next-intl";

import {apiPost} from "@/lib/api";
import {Card} from "@/components/ui";

export default function VerifyPage() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const common = useTranslations("common");
  const [status, setStatus] = useState<"verifying" | "success" | "error">("verifying");
  const [linkingCode, setLinkingCode] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    apiPost<{status: string}>(`/auth/verify/${token}`, {})
      .then((result) => {
        setStatus("success");
        if (result.status && result.status !== "verified") {
          setLinkingCode(result.status);
        }
      })
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-sm text-center">
        {status === "verifying" && (
          <div className="py-8">
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-accent" />
            <p className="mt-4 text-sm text-gray-500 dark:text-slate-400">{common("loading")}</p>
          </div>
        )}

        {status === "error" && (
          <div className="py-8">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/40">
              <svg className="h-6 w-6 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="mt-4 text-lg font-bold">{common("error")}</h1>
            <p className="mt-2 text-sm text-gray-500 dark:text-slate-400">
              Token is invalid or expired. Please request a new verification link.
            </p>
          </div>
        )}

        {status === "success" && (
          <div className="py-8">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/40">
              <svg className="h-6 w-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="mt-4 text-lg font-bold">Email Verified!</h1>
            {linkingCode && (
              <div className="mt-4">
                <p className="text-sm text-gray-600 dark:text-slate-400">
                  To connect your messaging account, send this code to the bot:
                </p>
                <code className="mt-2 inline-block rounded-lg bg-gray-100 px-4 py-2 font-mono text-lg font-bold dark:bg-slate-700">
                  {linkingCode}
                </code>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
