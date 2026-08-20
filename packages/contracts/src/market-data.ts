import type {
  AvailabilityWindow,
  CalendarDate,
  DecimalString,
  SourceAttribution,
} from "./common";

/** One regular-session daily bar. Prices and volume must not be mixed across adjustment bases. */
export interface DailyPriceBar {
  contractVersion: "v1";
  securityId: string;
  sessionDate: CalendarDate;
  session: "regular";
  currency: "USD";
  open: DecimalString;
  high: DecimalString;
  low: DecimalString;
  close: DecimalString;
  volume: DecimalString;
  adjustmentBasis: "unadjusted" | "split_adjusted" | "total_return_adjusted";
  availability: AvailabilityWindow;
  source: SourceAttribution;
}

export interface CorporateAction {
  contractVersion: "v1";
  providerActionId: string;
  securityId: string;
  actionType: string;
  processDate: CalendarDate;
  effectiveDate?: CalendarDate;
  cashAmount?: DecimalString;
  ratioNumerator?: DecimalString;
  ratioDenominator?: DecimalString;
  currency?: "USD";
  availability: AvailabilityWindow;
  source: SourceAttribution;
}
