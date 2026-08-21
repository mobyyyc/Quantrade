"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function DailyUpdateControl() {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "running" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  async function runUpdate() {
    setStatus("running");
    setMessage("Fetching prices and calculating today’s research scores. This can take a few minutes.");
    try {
      const response = await fetch("/api/v1/operations/daily-update", { method: "POST" });
      const body = await response.json() as { message?: string; error?: string };
      if (!response.ok) throw new Error(body.error || "The daily update did not complete.");
      setStatus("success");
      setMessage(body.message || "Daily update completed.");
      router.refresh();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The daily update did not complete.");
    }
  }
  return <section className="daily-update-control" aria-labelledby="daily-update-title">
    <div><p className="eyebrow">PRIVATE OPERATIONS</p><h2 id="daily-update-title">Refresh today’s research</h2><p>After market close, fetch current prices and calculate the latest evidence-backed scores.</p></div>
    <div className="daily-update-action"><button type="button" className="primary-link" onClick={runUpdate} disabled={status === "running"}>{status === "running" ? "Updating…" : "Run daily update"}</button>{status !== "idle" && <p className={`daily-update-message ${status}`} role="status">{message}</p>}</div>
  </section>;
}
