"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function AccountControl() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  async function signOut() {
    setPending(true);
    await fetch("/api/v1/auth/session", { method: "DELETE" });
    router.replace("/sign-in");
    router.refresh();
  }
  return <button type="button" className="account-control" onClick={() => void signOut()} disabled={pending}>
    {pending ? "Signing out…" : "Sign out"}
  </button>;
}
