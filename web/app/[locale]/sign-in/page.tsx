"use client";

import {FormEvent, useState} from "react";
import {useLocale} from "next-intl";

import {Card} from "@/components/ui";
import {apiPost} from "@/lib/api";

export default function SignInPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "sent" | "error">("idle");
  const locale = useLocale();

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setStatus("loading");
    try {
      await apiPost("/auth/subscribe", {
        email,
        locale,
        messaging_account_ref: `web-${crypto.randomUUID()}`,
      });
      setStatus("sent");
    } catch {
      setStatus("error");
    }
  };

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <h1 className="text-center text-xl font-bold">Sign in</h1>
        <p className="mt-1 text-center text-sm text-gray-500 dark:text-slate-400">
          Enter your email to receive a verification link
        </p>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-slate-300">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-gray-400 focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-slate-600 dark:bg-slate-800 dark:placeholder:text-slate-500"
              placeholder="you@example.com"
            />
          </div>
          <button
            type="submit"
            disabled={status === "loading"}
            className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
          >
            {status === "loading" ? "Sending..." : "Send verification link"}
          </button>
        </form>
        {status === "sent" && (
          <p className="mt-3 text-center text-sm text-green-600 dark:text-green-400">
            Check your email for the sign-in link.
          </p>
        )}
        {status === "error" && (
          <p className="mt-3 text-center text-sm text-red-600 dark:text-red-400">
            Could not send sign-in link. Please try again.
          </p>
        )}
      </Card>
    </div>
  );
}
