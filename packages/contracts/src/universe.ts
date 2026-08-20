import type {
  CalendarDate,
  DataCapabilityTier,
  SourceAttribution,
  UtcTimestamp,
} from "./common";

/** A dated membership claim, never an inferred historical constituent list. */
export interface UniverseMembershipSnapshot {
  contractVersion: "v1";
  universeCode: string;
  asOfDate: CalendarDate;
  securityId: string;
  historicalMembershipVerified: boolean;
  dataCapabilityTier: DataCapabilityTier;
  source: SourceAttribution;
  ingestedAt: UtcTimestamp;
}
