"use client";

import {FormEvent, useState} from "react";
import {signIn} from "next-auth/react";

import {Card} from "@/components/ui";

export default function SignInPage() {
  const [email, setEmail] = useState("");

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await signIn("credentials", {email, callbackUrl: "/en/dashboard"});
  };

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <h1 className="text-center text-xl font-bold">Sign in</h1>
        <p className="mt-1 text-center text-sm text-gray-500 dark:text-slate-400">
          Enter your email to continue
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
            className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
          >
            Continue
          </button>
        </form>
      </Card>
    </div>
  );
}
