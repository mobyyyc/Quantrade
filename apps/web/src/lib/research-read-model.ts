import { Pool } from "pg";

export type DatedScore = {
  scoreSnapshotId: string;
  securityId: string;
  scoreDate: string;
  decisionAt: string;
  publishedAt?: string;
  score: string;
  rank?: number;
  eligible: boolean;
  signal: "positive" | "neutral" | "negative" | "unavailable";
  modelVersion: string;
  featureVersion: string;
  protocolVersion: string;
  dataCutoffAt: string;
  dataCapabilityTier: "A" | "B" | "C";
  unavailableReason?: string;
};

export type ModelCard = {
  modelVersion: string;
  status: "research_only" | "private_beta_approved" | "rejected";
  protocolVersion: string;
  featureRegistryHash: string;
  dataCapabilityTier: "A" | "B" | "C";
  createdAt: string;
  purpose: string;
  methodology: string;
  limitations: string[];
  evaluationUri?: string;
};

export type SecuritySearchResult = {
  securityId: string;
  issuerName: string;
  ticker: string;
};

export type DailyPricePoint = {
  sessionDate: string;
  closePrice: string;
};

export type ScoreExplanation = {
  featureKey: string;
  featureVersion: string;
  sectorCode: string;
  percentile?: string;
  weight: string;
  contribution?: string;
  unavailableReason?: string;
  displayName?: string;
};

export class ResearchReadModelError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

let pool: Pool | undefined;

function databasePool(): Pool {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new ResearchReadModelError("Research data is not configured.", 503);
  }
  pool ??= new Pool({ connectionString });
  return pool;
}

function scoreFromRow(row: Record<string, unknown>): DatedScore {
  return {
    scoreSnapshotId: String(row.score_snapshot_id),
    securityId: String(row.security_id),
    scoreDate: String(row.score_date),
    decisionAt: new Date(String(row.decision_at)).toISOString(),
    ...(row.published_at
      ? { publishedAt: new Date(String(row.published_at)).toISOString() }
      : {}),
    score: String(row.score),
    ...(row.rank === null ? {} : { rank: Number(row.rank) }),
    eligible: Boolean(row.eligible),
    signal: row.signal as DatedScore["signal"],
    modelVersion: String(row.model_version),
    featureVersion: String(row.feature_version),
    protocolVersion: String(row.protocol_version),
    dataCutoffAt: new Date(String(row.data_cutoff_at)).toISOString(),
    dataCapabilityTier: row.data_capability_tier as DatedScore["dataCapabilityTier"],
    ...(row.unavailable_reason
      ? { unavailableReason: String(row.unavailable_reason) }
      : {}),
  };
}

export async function listDatedScores(scoreDate: string): Promise<DatedScore[]> {
  const result = await databasePool().query(
    `SELECT score_snapshot_id, security_id, score_date::text AS score_date, decision_at, published_at, score, rank,
            eligible, signal, model_version, feature_version, protocol_version, data_cutoff_at,
            data_capability_tier, unavailable_reason
     FROM quantrade.score_snapshots
     WHERE score_date = $1
     ORDER BY eligible DESC, rank ASC NULLS LAST, security_id ASC`,
    [scoreDate],
  );
  return result.rows.map(scoreFromRow);
}

export async function getDatedScore(
  securityId: string,
  scoreDate: string,
): Promise<DatedScore | null> {
  const result = await databasePool().query(
    `SELECT score_snapshot_id, security_id, score_date::text AS score_date, decision_at, published_at, score, rank,
            eligible, signal, model_version, feature_version, protocol_version, data_cutoff_at,
            data_capability_tier, unavailable_reason
     FROM quantrade.score_snapshots
     WHERE security_id = $1 AND score_date = $2
     ORDER BY decision_at DESC
     LIMIT 1`,
    [securityId, scoreDate],
  );
  return result.rowCount === 0 ? null : scoreFromRow(result.rows[0]);
}

export async function getModelCard(modelVersion: string): Promise<ModelCard | null> {
  const result = await databasePool().query(
    `SELECT model_version, status, protocol_version, feature_registry_hash, data_capability_tier,
            created_at, purpose, methodology, limitations, evaluation_uri
     FROM quantrade.model_cards
     WHERE model_version = $1`,
    [modelVersion],
  );
  if (result.rowCount === 0) {
    return null;
  }
  const row = result.rows[0] as Record<string, unknown>;
  const limitations = Array.isArray(row.limitations)
    ? row.limitations.map(String)
    : JSON.parse(String(row.limitations)) as string[];
  return {
    modelVersion: String(row.model_version),
    status: row.status as ModelCard["status"],
    protocolVersion: String(row.protocol_version),
    featureRegistryHash: String(row.feature_registry_hash),
    dataCapabilityTier: row.data_capability_tier as ModelCard["dataCapabilityTier"],
    createdAt: new Date(String(row.created_at)).toISOString(),
    purpose: String(row.purpose),
    methodology: String(row.methodology),
    limitations,
    ...(row.evaluation_uri ? { evaluationUri: String(row.evaluation_uri) } : {}),
  };
}

export async function getLatestDatedScores(): Promise<{
  scoreDate: string;
  scores: DatedScore[];
} | null> {
  const result = await databasePool().query<{ score_date: string }>(
    "SELECT MAX(score_date)::text AS score_date FROM quantrade.score_snapshots",
  );
  const scoreDate = result.rows[0]?.score_date;
  return scoreDate ? { scoreDate, scores: await listDatedScores(scoreDate) } : null;
}

export async function searchSecurities(query: string): Promise<SecuritySearchResult[]> {
  const term = query.trim();
  if (!term) {
    return [];
  }
  const result = await databasePool().query(
    `SELECT s.security_id, s.issuer_name, l.ticker
     FROM quantrade.securities s
     JOIN quantrade.listings l ON l.security_id = s.security_id
     WHERE l.valid_to IS NULL
       AND (l.ticker ILIKE $1 OR s.issuer_name ILIKE $1)
     ORDER BY CASE WHEN l.ticker ILIKE $2 THEN 0 ELSE 1 END, l.ticker ASC
     LIMIT 12`,
    [`%${term}%`, `${term}%`],
  );
  return result.rows.map((row) => ({
    securityId: String(row.security_id),
    issuerName: String(row.issuer_name),
    ticker: String(row.ticker),
  }));
}

export async function getSecurityIdentity(securityId: string): Promise<SecuritySearchResult | null> {
  const result = await databasePool().query(
    `SELECT s.security_id, s.issuer_name, l.ticker
     FROM quantrade.securities s
     JOIN quantrade.listings l ON l.security_id = s.security_id
     WHERE s.security_id = $1 AND l.valid_to IS NULL
     ORDER BY l.valid_from DESC
     LIMIT 1`,
    [securityId],
  );
  if (result.rowCount === 0) {
    return null;
  }
  const row = result.rows[0] as Record<string, unknown>;
  return {
    securityId: String(row.security_id),
    issuerName: String(row.issuer_name),
    ticker: String(row.ticker),
  };
}

export async function getDailyPriceHistory(
  securityId: string,
  limit = 180,
): Promise<DailyPricePoint[]> {
  const result = await databasePool().query(
    `SELECT session_date::text, close_price
     FROM (
       SELECT session_date, close_price
       FROM quantrade.daily_price_bars
       WHERE security_id = $1
         AND adjustment_basis = 'split_adjusted'
         AND session = 'regular'
       ORDER BY session_date DESC
       LIMIT $2
     ) recent
     ORDER BY session_date ASC`,
    [securityId, limit],
  );
  return result.rows.map((row) => ({
    sessionDate: String(row.session_date),
    closePrice: String(row.close_price),
  }));
}

export async function getScoreExplanations(
  securityId: string,
  scoreDate: string,
): Promise<ScoreExplanation[]> {
  const result = await databasePool().query(
    `SELECT e.feature_key, e.feature_version, e.sector_code, e.percentile, e.feature_weight,
            e.contribution, e.unavailable_reason, d.display_name
     FROM quantrade.score_explanations e
     JOIN quantrade.score_snapshots s ON s.score_snapshot_id = e.score_snapshot_id
     LEFT JOIN quantrade.feature_definitions d
       ON d.feature_key = e.feature_key
      AND d.feature_version = e.feature_version
      AND d.definition_hash = e.definition_hash
     WHERE s.security_id = $1 AND s.score_date = $2
     ORDER BY e.contribution DESC NULLS LAST, e.feature_key ASC`,
    [securityId, scoreDate],
  );
  return result.rows.map((row) => ({
    featureKey: String(row.feature_key),
    featureVersion: String(row.feature_version),
    sectorCode: String(row.sector_code),
    ...(row.percentile === null ? {} : { percentile: String(row.percentile) }),
    weight: String(row.feature_weight),
    ...(row.contribution === null ? {} : { contribution: String(row.contribution) }),
    ...(row.unavailable_reason ? { unavailableReason: String(row.unavailable_reason) } : {}),
    ...(row.display_name ? { displayName: String(row.display_name) } : {}),
  }));
}
