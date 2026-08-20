/** ISO 8601 timestamp in UTC, for example `2026-08-20T20:00:00Z`. */
export type UtcTimestamp = string;

/** ISO 8601 calendar date, for example `2026-08-20`. */
export type CalendarDate = string;

/**
 * A decimal encoded as a string. This prevents JavaScript floating-point
 * conversion from changing financial values at the API boundary.
 */
export type DecimalString = string;

export type SourceProvider =
  | "sec_edgar"
  | "alpaca"
  | "fred"
  | "alfred"
  | "manual";

export type DataCapabilityTier = "A" | "B" | "C";

export interface SourceAttribution {
  provider: SourceProvider;
  sourceReference: string;
  retrievedAt: UtcTimestamp;
  rawArtifactUri: string;
}

export interface AvailabilityWindow {
  observedAt?: UtcTimestamp;
  publishedAt?: UtcTimestamp;
  availableAt: UtcTimestamp;
  ingestedAt: UtcTimestamp;
}
