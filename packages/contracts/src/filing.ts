import type {
  AvailabilityWindow,
  CalendarDate,
  DecimalString,
  SourceAttribution,
  UtcTimestamp,
} from "./common";

export interface FilingRecord {
  contractVersion: "v1";
  filingId: string;
  securityId: string;
  accessionNumber: string;
  form: "10-K" | "10-Q" | "8-K" | "20-F" | "40-F" | "other";
  filedAt: UtcTimestamp;
  acceptedAt: UtcTimestamp;
  periodEnd?: CalendarDate;
  availability: AvailabilityWindow;
  source: SourceAttribution;
}

/** A normalized XBRL fact, linked to the filing that made it available. */
export interface FilingFact {
  contractVersion: "v1";
  factId: string;
  filingId: string;
  securityId: string;
  taxonomy: string;
  concept: string;
  unit: string;
  value: DecimalString;
  periodStart?: CalendarDate;
  periodEnd: CalendarDate;
  fiscalYear?: number;
  fiscalPeriod?: "FY" | "Q1" | "Q2" | "Q3" | "Q4";
  availability: AvailabilityWindow;
  source: SourceAttribution;
}
