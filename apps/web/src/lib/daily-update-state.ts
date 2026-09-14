export type DailyOperationRunStatus = "running" | "completed" | "failed" | "skipped";

export type DailyOperationState =
  | "running"
  | "retrying"
  | "complete"
  | "partial"
  | "skipped"
  | "duplicate_prevented"
  | "failed";

export type PublicationFreshness = "current" | "stale" | "misaligned" | "unavailable";

export function deriveDailyOperationState({
  status,
  lastEventType,
  unresolvedWarningCount,
}: {
  status: DailyOperationRunStatus;
  lastEventType?: string;
  unresolvedWarningCount: number;
}): DailyOperationState {
  if (status === "failed") return "failed";
  if (status === "skipped") return "skipped";
  if (status === "running") return lastEventType === "provider_retry" ? "retrying" : "running";
  if (unresolvedWarningCount > 0) return "partial";
  if (lastEventType === "duplicate_prevented") return "duplicate_prevented";
  return "complete";
}

export function derivePublicationFreshness({
  scoreDate,
  marketSession,
  benchmarkSession,
}: {
  scoreDate?: string;
  marketSession?: string;
  benchmarkSession?: string;
}): PublicationFreshness {
  if (!scoreDate || !marketSession || !benchmarkSession) return "unavailable";
  if (marketSession !== benchmarkSession) return "misaligned";
  return scoreDate < marketSession ? "stale" : "current";
}

export function safeDailyUpdateError(output: string): string {
  if (output.includes("available after the regular market closes")) {
    return "The daily update is available after the regular market closes at 4:00 p.m. Toronto time.";
  }
  if (output.includes("No current S&P 500 universe")) {
    return "Today’s S&P 500 universe is not ready yet. Try again after the daily data refresh.";
  }
  if (output.includes("already running")) {
    return "A daily update is already running. Check Recent daily updates for its recorded state before trying again.";
  }
  if (output.includes("has not been published yet")) {
    return "SEC has not published today’s daily filing index yet. Retry after 10:00 p.m. Toronto time; no scores were published.";
  }
  if (output.includes("after 3 attempts")) {
    return "A data provider remained unavailable after three safe attempts. No scores were published; try again later.";
  }
  if (output.includes("SEC filing ingestion failed")) {
    return "SEC filing retrieval or validation did not complete. The update stopped safely before publication; no duplicate scores were created.";
  }
  return "The daily update stopped safely before publication. Review the local service log, then retry.";
}

export function operationStateLabel(state: DailyOperationState): string {
  return {
    running: "In progress",
    retrying: "Retrying provider",
    complete: "Complete",
    partial: "Scores ready, maintenance pending",
    skipped: "No market session",
    duplicate_prevented: "Duplicate prevented",
    failed: "Needs attention",
  }[state];
}

export function publicationFreshnessLabel(state: PublicationFreshness): string {
  return {
    current: "Aligned with stored market data",
    stale: "Newer market data is awaiting publication",
    misaligned: "Stock and SPY dates do not align",
    unavailable: "Freshness is unavailable",
  }[state];
}
