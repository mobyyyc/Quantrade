"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { formatResearchDate } from "@/lib/format";

type UpdateSummary = {
  scoreDate: string;
  eligibleCount: number;
  totalCount: number;
};

export function DailyUpdateControl() {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "running" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [summary, setSummary] = useState<UpdateSummary | null>(null);
  async function runUpdate() {
    setStatus("running");
    setSummary(null);
    setMessage("Update in progress: current prices are being checked, then eligible scores will be published.");
    try {
      const response = await fetch("/api/v1/operations/daily-update", { method: "POST" });
      const body = await response.json() as { message?: string; error?: string; result?: UpdateSummary };
      if (!response.ok) throw new Error(body.error || "The daily update did not complete.");
      setStatus("success");
      setMessage(body.message || "Daily update completed.");
      setSummary(body.result ?? null);
      router.refresh();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The daily update did not complete.");
    }
  }
  const withheldCount = summary ? summary.totalCount - summary.eligibleCount : 0;
  const coverage = summary?.totalCount ? Math.round((summary.eligibleCount / summary.totalCount) * 100) : 0;
  return <section className="daily-update" aria-labelledby="daily-update-title" aria-busy={status === "running"}>
    <div className="daily-update-control"><div><p className="eyebrow">PRIVATE OPERATIONS</p><h2 id="daily-update-title">Refresh today’s research</h2><p>After market close, validate current prices, calculate eligible scores, then publish the dated result.</p></div><div className="daily-update-action"><button type="button" className="primary-link" onClick={runUpdate} disabled={status === "running"}>{status === "running" ? "Updating…" : "Run daily update"}</button>{status !== "idle" && <p className={`daily-update-message ${status}`} role="status">{message}</p>}</div></div>
    {summary && <div className="daily-update-summary" role="status"><div><p className="eyebrow">DAILY UPDATE COMPLETE</p><h3>Research for {formatResearchDate(summary.scoreDate)} is ready.</h3><p>The new dated result is available across Today, Rankings, and your Watchlist.</p></div><dl><div><dt>Eligible</dt><dd>{summary.eligibleCount}</dd></div><div><dt>Withheld</dt><dd>{withheldCount}</dd></div><div><dt>Coverage</dt><dd>{coverage}%</dd></div></dl><Link href={`/rankings?date=${summary.scoreDate}`} className="text-link">Review rankings</Link></div>}
  </section>;
}
