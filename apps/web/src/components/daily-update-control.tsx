"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { formatPublicationTime, formatResearchDate } from "@/lib/format";
import type {
  DailyUpdateOutcome,
  DailyUpdateProgressStage,
  DailyUpdateStreamEvent,
  DailyUpdateSummary,
} from "@/lib/daily-update-progress";
import { operationStateLabel, publicationFreshnessLabel } from "@/lib/daily-update-state";
import type { DailyOperationsStatus } from "@/lib/research-read-model";

const STAGE_LABELS: Record<DailyUpdateProgressStage, string> = {
  initialization: "Preparing",
  market_data: "Market data",
  sec_filings: "SEC filings",
  validation: "Validation",
  scoring: "Scoring",
  portfolio: "Portfolio",
  completion: "Finishing",
};

type UiStatus = "idle" | "running" | "retrying" | "success" | "partial" | "skipped" | "duplicate" | "error";
type Completion = { outcome: DailyUpdateOutcome; message: string; result?: DailyUpdateSummary };

function completionStatus(outcome: DailyUpdateOutcome): UiStatus {
  if (outcome === "partial") return "partial";
  if (outcome === "skipped") return "skipped";
  if (outcome === "duplicate_prevented") return "duplicate";
  return "success";
}

function completionTitle(completion: Completion): string {
  if (completion.outcome === "skipped") return "No publication was needed.";
  if (completion.outcome === "duplicate_prevented") return "Nothing was duplicated.";
  return completion.result
    ? `Research for ${formatResearchDate(completion.result.scoreDate)} is ready.`
    : "The update finished safely.";
}

function completionLabel(outcome: DailyUpdateOutcome): string {
  return {
    complete: "DAILY UPDATE COMPLETE",
    partial: "SCORES READY · MAINTENANCE PENDING",
    skipped: "UPDATE SKIPPED",
    duplicate_prevented: "DUPLICATE PREVENTED",
  }[outcome];
}

export function DailyUpdateControl({ operations }: { operations: DailyOperationsStatus }) {
  const router = useRouter();
  const [status, setStatus] = useState<UiStatus>("idle");
  const [message, setMessage] = useState("");
  const [completion, setCompletion] = useState<Completion | null>(null);

  async function runUpdate() {
    setStatus("running");
    setCompletion(null);
    setMessage("Preparing the locked daily update.");
    try {
      const response = await fetch("/api/v1/operations/daily-update", { method: "POST" });
      if (!response.ok || !response.body) {
        const body = await response.json() as { error?: string };
        throw new Error(body.error || "The daily update stopped safely before publication.");
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
            setStatus(event.progress.status === "retrying" ? "retrying" : "running");
            setMessage(`${STAGE_LABELS[event.progress.stage]}: ${event.progress.message}`);
          } else if (event.type === "error") {
            throw new Error(event.error);
          } else {
            completed = true;
            setStatus(completionStatus(event.outcome));
            setMessage(event.message);
            setCompletion({ outcome: event.outcome, message: event.message, ...(event.result ? { result: event.result } : {}) });
          }
        }
        if (done) break;
      }
      if (!completed) throw new Error("The update connection closed before a terminal state was recorded. Check Recent daily updates before retrying.");
      router.refresh();
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "The daily update stopped safely before publication.");
    }
  }

  const summary = completion?.result;
  const withheldCount = summary ? summary.totalCount - summary.eligibleCount : 0;
  const coverage = summary?.totalCount ? Math.round((summary.eligibleCount / summary.totalCount) * 100) : 0;
  const active = status === "running" || status === "retrying";
  const latestRun = operations.latestRun;
  const showInlineStatus = status !== "idle" && completion === null;

  return <section className="daily-update" aria-labelledby="daily-update-title" aria-busy={active}>
    <div className="daily-update-control">
      <div><p className="eyebrow">PRIVATE OPERATIONS</p><h2 id="daily-update-title">Refresh today’s research</h2><p>After market close, validate new evidence and publish one dated result. Repeats are safely deduplicated.</p></div>
      <div className="daily-update-action"><button type="button" className="primary-link" onClick={runUpdate} disabled={active}>{status === "retrying" ? "Retrying provider…" : status === "running" ? "Updating…" : status === "partial" ? "Retry maintenance" : "Run daily update"}</button><p className={`daily-update-message ${status}`} role={showInlineStatus ? status === "error" ? "alert" : "status" : undefined} aria-live={status === "error" ? "assertive" : "polite"} aria-atomic="true" aria-hidden={!showInlineStatus}>{showInlineStatus ? message : "Daily update status"}</p></div>
    </div>
    <dl className="daily-update-record" aria-label="Recorded daily update status">
      <div><dt>Last recorded state</dt><dd>{latestRun ? operationStateLabel(latestRun.state) : "Waiting for first run"}<span>{latestRun ? `${formatResearchDate(latestRun.scoreDate)} · ${formatPublicationTime(latestRun.lastEventAt)}` : "No operation has been recorded."}</span></dd></div>
      <div><dt>Published research</dt><dd>{operations.latestPublishedScoreDate ? formatResearchDate(operations.latestPublishedScoreDate) : "Unavailable"}<span>{publicationFreshnessLabel(operations.publicationFreshness)}</span></dd></div>
      <div><dt>Source freshness</dt><dd>{operations.latestMarketSession ? `Market ${formatResearchDate(operations.latestMarketSession)}` : "Market unavailable"}<span>{operations.latestSecRefreshAt ? `SEC checked ${formatPublicationTime(operations.latestSecRefreshAt)}` : "SEC refresh unavailable"}</span></dd></div>
    </dl>
    {completion && <div className={`daily-update-summary ${completion.outcome}`} role="status"><div><p className="eyebrow">{completionLabel(completion.outcome)}</p><h3>{completionTitle(completion)}</h3><p>{completion.message}</p></div>{summary && <dl><div><dt>Eligible</dt><dd>{summary.eligibleCount}</dd></div><div><dt>Withheld</dt><dd>{withheldCount}</dd></div><div><dt>Coverage</dt><dd>{coverage}%</dd></div></dl>}{summary && <Link href={`/rankings?date=${summary.scoreDate}`} className="text-link">Review rankings</Link>}</div>}
  </section>;
}
