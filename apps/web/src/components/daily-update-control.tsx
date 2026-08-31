"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { formatResearchDate } from "@/lib/format";
import type {
  DailyUpdateProgressStage,
  DailyUpdateStreamEvent,
  DailyUpdateSummary,
} from "@/lib/daily-update-progress";

const STAGE_LABELS: Record<DailyUpdateProgressStage, string> = {
  initialization: "Preparing",
  market_data: "Market data",
  sec_filings: "SEC filings",
  validation: "Validation",
  scoring: "Scoring",
  portfolio: "Portfolio",
  completion: "Complete",
};

export function DailyUpdateControl() {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "running" | "success" | "error">("idle");
  const [message, setMessage] = useState("");
  const [summary, setSummary] = useState<DailyUpdateSummary | null>(null);
  async function runUpdate() {
    setStatus("running");
    setSummary(null);
    setMessage("Update in progress: current prices are being checked, then eligible scores will be published.");
    try {
      const response = await fetch("/api/v1/operations/daily-update", { method: "POST" });
      if (!response.ok || !response.body) {
        const body = await response.json() as { error?: string };
        throw new Error(body.error || "The daily update did not complete.");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completed = false;
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line) as DailyUpdateStreamEvent;
          if (event.type === "progress") {
            setMessage(`${STAGE_LABELS[event.progress.stage]}: ${event.progress.message}`);
          } else if (event.type === "error") {
            throw new Error(event.error);
          } else {
            completed = true;
            setStatus("success");
            setMessage(event.message);
            setSummary(event.result ?? null);
          }
        }
        if (done) break;
      }
      if (!completed) throw new Error("The daily update connection closed before completion.");
      router.refresh();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The daily update did not complete.");
    }
  }
  const withheldCount = summary ? summary.totalCount - summary.eligibleCount : 0;
  const coverage = summary?.totalCount ? Math.round((summary.eligibleCount / summary.totalCount) * 100) : 0;
  return <section className="daily-update" aria-labelledby="daily-update-title" aria-busy={status === "running"}>
    <div className="daily-update-control"><div><p className="eyebrow">PRIVATE OPERATIONS</p><h2 id="daily-update-title">Refresh today’s research</h2><p>After market close, validate current prices, calculate eligible scores, then publish the dated result.</p></div><div className="daily-update-action"><button type="button" className="primary-link" onClick={runUpdate} disabled={status === "running"}>{status === "running" ? "Updating…" : "Run daily update"}</button><p className={`daily-update-message ${status}`} role={status === "idle" ? undefined : "status"} aria-live="polite" aria-atomic="true" aria-hidden={status === "idle"}>{message || "Daily update status"}</p></div></div>
    {summary && <div className="daily-update-summary" role="status"><div><p className="eyebrow">DAILY UPDATE COMPLETE</p><h3>Research for {formatResearchDate(summary.scoreDate)} is ready.</h3><p>The new dated result is available across Today, Rankings, and your Watchlist.</p></div><dl><div><dt>Eligible</dt><dd>{summary.eligibleCount}</dd></div><div><dt>Withheld</dt><dd>{withheldCount}</dd></div><div><dt>Coverage</dt><dd>{coverage}%</dd></div></dl><Link href={`/rankings?date=${summary.scoreDate}`} className="text-link">Review rankings</Link></div>}
  </section>;
}
