"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

export function SignInForm({ setupRequired, nextPath }: { setupRequired: boolean; nextPath: string }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch(setupRequired ? "/api/v1/auth/setup" : "/api/v1/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: data.get("email"), password: data.get("password") }),
      });
      const body = await response.json() as { error?: string };
      if (!response.ok) throw new Error(body.error || "Sign-in failed.");
      router.replace(nextPath);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign-in failed.");
      setPending(false);
    }
  }

  return <form className="auth-form" onSubmit={submit}>
    <label>Email<input name="email" type="email" autoComplete="email" required autoFocus /></label>
    <label>Password<input name="password" type="password" autoComplete={setupRequired ? "new-password" : "current-password"} minLength={12} required /></label>
    {setupRequired ? <p className="auth-hint">Choose at least 12 characters. This creates the only owner account on this computer.</p> : null}
    {error ? <p className="auth-error" role="alert">{error}</p> : null}
    <button className="primary-button" type="submit" disabled={pending}>{pending ? "Please wait…" : setupRequired ? "Create owner account" : "Sign in"}</button>
  </form>;
}
