import type {
  CalendarDate,
  SourceAttribution,
  UtcTimestamp,
} from "./common";

export interface SecurityIdentifier {
  identifierType: "ticker" | "cik" | "figi" | "isin";
  value: string;
}

/**
 * Stable instrument identity. A ticker is an identifier, not the primary key:
 * it can change or be reused over time.
 */
export interface SecurityRecord {
  contractVersion: "v1";
  securityId: string;
  issuerName: string;
  assetClass: "common_stock";
  countryCode: "US";
  identifiers: SecurityIdentifier[];
  validFrom: CalendarDate;
  validTo?: CalendarDate;
  source: SourceAttribution;
  ingestedAt: UtcTimestamp;
}

export interface ListingRecord {
  contractVersion: "v1";
  listingId: string;
  securityId: string;
  ticker: string;
  exchangeMic: string;
  currency: "USD";
  validFrom: CalendarDate;
  validTo?: CalendarDate;
  source: SourceAttribution;
  ingestedAt: UtcTimestamp;
}
