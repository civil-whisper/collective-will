"use client";

import {useSearchParams} from "next/navigation";
import {useEffect, useState} from "react";
import {useTranslations} from "next-intl";

import {apiPost} from "@/lib/api";

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

  if (status === "verifying") {
    return <p>{common("loading")}</p>;
  }

  if (status === "error") {
    return (
      <section>
        <h1>{common("error")}</h1>
        <p>Token is invalid or expired. Please request a new verification link.</p>
      </section>
    );
  }

  return (
    <section>
      <h1>Email Verified!</h1>
      {linkingCode && (
        <div>
          <p>To connect WhatsApp, send this code to the bot:</p>
          <code style={{fontSize: "1.5rem", padding: "0.5rem 1rem", background: "#f0f0f0"}}>{linkingCode}</code>
        </div>
      )}
    </section>
  );
}
