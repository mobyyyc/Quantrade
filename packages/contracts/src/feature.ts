/** Immutable, versioned meaning of a feature used by a research model. */
export type FeatureFamily =
  | "momentum"
  | "value"
  | "profitability"
  | "risk"
  | "liquidity";

export type FeatureDirection = "higher_is_better" | "lower_is_better";

export interface FeatureDefinition {
  contractVersion: "v1";
  featureKey: string;
  featureVersion: string;
  family: FeatureFamily;
  direction: FeatureDirection;
  displayName: string;
  description: string;
  formula: string;
  requiredInputs: string[];
  asOfRule: string;
  definitionHash: string;
}
