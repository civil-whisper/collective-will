"use client";

import {FormEvent, useState} from "react";
import {signIn} from "next-auth/react";

export default function SignInPage() {
  const [email, setEmail] = useState("");

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await signIn("credentials", {email, callbackUrl: "/en/dashboard"});
  };

  return (
    <main>
      <h1>Sign in</h1>
      <form onSubmit={onSubmit}>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <button type="submit">Continue</button>
      </form>
    </main>
  );
}
