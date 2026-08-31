export const DAILY_UPDATE_PROGRESS_PREFIX = "QUANTRADE_PROGRESS ";

export type DailyUpdateProgressStage =
  | "initialization"
  | "market_data"
  | "sec_filings"
  | "validation"
  | "scoring"
  | "portfolio"
  | "completion";

export type DailyUpdateProgress = {
  contract: "daily_update_progress_v1";
  stage: DailyUpdateProgressStage;
  status: "started" | "completed" | "skipped" | "warning" | "failed";
  message: string;
  scoreDate?: string;
};

export type DailyUpdateSummary = {
  scoreDate: string;
  eligibleCount: number;
  totalCount: number;
};

export type DailyUpdateStreamEvent =
  | { type: "progress"; progress: DailyUpdateProgress }
  | { type: "complete"; message: string; result?: DailyUpdateSummary }
  | { type: "error"; error: string };

const STAGES = new Set<DailyUpdateProgressStage>([
  "initialization", "market_data", "sec_filings", "validation", "scoring", "portfolio", "completion",
]);
const STATUSES = new Set<DailyUpdateProgress["status"]>([
  "started", "completed", "skipped", "warning", "failed",
]);

export function parseDailyUpdateProgress(line: string): DailyUpdateProgress | null {
  if (!line.startsWith(DAILY_UPDATE_PROGRESS_PREFIX)) return null;
  try {
    const value = JSON.parse(line.slice(DAILY_UPDATE_PROGRESS_PREFIX.length)) as Partial<DailyUpdateProgress>;
    if (
      value.contract !== "daily_update_progress_v1"
      || !value.stage
      || !STAGES.has(value.stage)
      || !value.status
      || !STATUSES.has(value.status)
      || typeof value.message !== "string"
    ) return null;
    return value as DailyUpdateProgress;
  } catch {
    return null;
  }
}
