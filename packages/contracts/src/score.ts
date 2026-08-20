import type {
  CalendarDate,
  DataCapabilityTier,
  DecimalString,
  UtcTimestamp,
} from "./common";

export type ScoreSignal = "positive" | "neutral" | "negative" | "unavailable";

/**
 * Immutable, dated output of one approved model run for one security.
 * `score` is a calibrated rank display, never an expected return or advice.
 */
export interface ScoreSnapshot {
  contractVersion: "v1";
  scoreSnapshotId: string;
  securityId: string;
  scoreDate: CalendarDate;
  decisionAt: UtcTimestamp;
  publishedAt?: UtcTimestamp;
  score: DecimalString;
  rank?: number;
  eligible: boolean;
  signal: ScoreSignal;
  modelVersion: string;
  featureVersion: string;
  protocolVersion: string;
  dataCutoffAt: UtcTimestamp;
  dataCapabilityTier: DataCapabilityTier;
  unavailableReason?: string;
}
