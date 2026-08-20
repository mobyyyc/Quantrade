import type { DataCapabilityTier, UtcTimestamp } from "./common";

export type ModelCardStatus = "research_only" | "private_beta_approved" | "rejected";

/** A dated, immutable statement of a model's methodology and limitations. */
export interface ModelCard {
  contractVersion: "v1";
  modelVersion: string;
  status: ModelCardStatus;
  protocolVersion: string;
  featureRegistryHash: string;
  dataCapabilityTier: DataCapabilityTier;
  createdAt: UtcTimestamp;
  purpose: string;
  methodology: string;
  limitations: string[];
  evaluationUri?: string;
}
