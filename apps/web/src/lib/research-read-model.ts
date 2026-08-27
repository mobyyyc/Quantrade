import { Pool } from "pg";

export type DatedScore = {
  scoreSnapshotId: string;
  securityId: string;
  issuerName: string;
  ticker: string;
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

export type PaperPortfolioOutcome = {
  horizonSessions: number;
  status: "completed" | "withheld";
  outcomeDate: string;
  portfolioReturn?: string;
  benchmarkReturn?: string;
  benchmarkRelativeReturn?: string;
  unavailableReason?: string;
};

export type PaperPortfolio = {
  scoreDate: string;
  executionDate: string;
  startingNav: string;
  positions: Array<{ securityId: string; ticker: string; issuerName: string; quantity: string }>;
  outcomes: PaperPortfolioOutcome[];
};

export type DailyPricePoint = {
  sessionDate: string;
  closePrice: string;
};

export type LatestPriceSummary = {
  securityId: string;
  sessionDate: string;
  closePrice: string;
  previousClosePrice?: string;
};

export type StockAtAGlance = {
  sessionDate: string;
  closePrice: string;
  previousClosePrice?: string;
  marketValue?: string;
  sharesReportedFor?: string;
};

export type ScoreRunSummary = {
  scoreDate: string;
  publishedAt?: string;
  eligibleCount: number;
};

export type TodayFilingActivity = {
  securityId: string;
  issuerName: string;
  ticker: string;
  filingCount: number;
  forms: string[];
  latestAcceptedAt: string;
};

export type DailyOperationRunStatus = "running" | "completed" | "failed" | "skipped";

export type DailyOperationsStatus = {
  latestRun?: {
    scoreDate: string;
    status: DailyOperationRunStatus;
    decisionAt?: string;
    completedAt?: string;
    eligibleCount?: number;
    failureReason?: string;
  };
  latestMarketSession?: string;
  latestBenchmarkSession?: string;
  latestSecRefreshAt?: string;
};

export type ForwardOutcomeReadiness = {
  horizonSessions: number;
  completedLabels: number;
  withheldLabels: number;
  pendingLabels: number;
  completedScoreDates: number;
  latestOutcomeDate?: string;
};

export const ML_DATASET_MINIMUM_COMPLETED_LABELS = 5000;
export const ML_DATASET_MINIMUM_SCORE_DATES = 126;

export type ScoreHistoryPoint = {
  scoreDate: string;
  score: string;
  rank?: number;
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
    issuerName: row.issuer_name ? String(row.issuer_name) : "Unknown company",
    ticker: row.ticker ? String(row.ticker) : "Unavailable",
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
    `SELECT ss.score_snapshot_id, ss.security_id, s.issuer_name, l.ticker, ss.score_date::text AS score_date, ss.decision_at, ss.published_at, ss.score, ss.rank,
            eligible, signal, model_version, feature_version, protocol_version, data_cutoff_at,
            data_capability_tier, unavailable_reason
     FROM quantrade.score_snapshots ss
     JOIN quantrade.daily_research_runs run
       ON run.score_date = ss.score_date
      AND run.decision_at = ss.decision_at
      AND run.status = 'completed'
     LEFT JOIN quantrade.securities s ON s.security_id = ss.security_id
     LEFT JOIN LATERAL (
       SELECT ticker
       FROM quantrade.listings
       WHERE security_id = ss.security_id
         AND valid_from <= ss.score_date
         AND (valid_to IS NULL OR valid_to > ss.score_date)
       ORDER BY valid_from DESC
       LIMIT 1
     ) l ON TRUE
     WHERE ss.score_date = $1
     ORDER BY ss.eligible DESC, ss.rank ASC NULLS LAST, ss.security_id ASC`,
    [scoreDate],
  );
  return result.rows.map(scoreFromRow);
}

export async function getDatedScore(
  securityId: string,
  scoreDate: string,
): Promise<DatedScore | null> {
  const result = await databasePool().query(
    `SELECT ss.score_snapshot_id, ss.security_id, s.issuer_name, l.ticker, ss.score_date::text AS score_date, ss.decision_at, ss.published_at, ss.score, ss.rank,
            eligible, signal, model_version, feature_version, protocol_version, data_cutoff_at,
            data_capability_tier, unavailable_reason
     FROM quantrade.score_snapshots ss
     JOIN quantrade.daily_research_runs run
       ON run.score_date = ss.score_date
      AND run.decision_at = ss.decision_at
      AND run.status = 'completed'
     LEFT JOIN quantrade.securities s ON s.security_id = ss.security_id
     LEFT JOIN LATERAL (
       SELECT ticker
       FROM quantrade.listings
       WHERE security_id = ss.security_id
         AND valid_from <= ss.score_date
         AND (valid_to IS NULL OR valid_to > ss.score_date)
       ORDER BY valid_from DESC
       LIMIT 1
     ) l ON TRUE
     WHERE ss.security_id = $1 AND ss.score_date = $2
     ORDER BY ss.decision_at DESC
     LIMIT 1`,
    [securityId, scoreDate],
  );
  return result.rowCount === 0 ? null : scoreFromRow(result.rows[0]);
}

export async function getScoreHistory(
  securityId: string,
  throughDate: string,
  limit = 8,
): Promise<ScoreHistoryPoint[]> {
  const result = await databasePool().query(
    `SELECT recent.score_date::text AS score_date, recent.score, recent.rank
     FROM (
        SELECT ss.score_date, ss.score, ss.rank
        FROM quantrade.score_snapshots ss
        JOIN quantrade.daily_research_runs run
          ON run.score_date = ss.score_date
         AND run.decision_at = ss.decision_at
         AND run.status = 'completed'
        WHERE ss.security_id = $1
          AND ss.score_date <= $2
          AND ss.eligible
        ORDER BY ss.score_date DESC
       LIMIT $3
     ) recent
     ORDER BY score_date ASC`,
    [securityId, throughDate, limit],
  );
  return result.rows.map((row) => ({
    scoreDate: String(row.score_date),
    score: String(row.score),
    ...(row.rank === null ? {} : { rank: Number(row.rank) }),
  }));
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
    "SELECT MAX(score_date)::text AS score_date FROM quantrade.daily_research_runs WHERE status = 'completed'",
  );
  const scoreDate = result.rows[0]?.score_date;
  return scoreDate ? { scoreDate, scores: await listDatedScores(scoreDate) } : null;
}

export async function getPreviousDatedScores(beforeDate: string): Promise<{
  scoreDate: string;
  scores: DatedScore[];
} | null> {
  const result = await databasePool().query<{ score_date: string }>(
    "SELECT MAX(score_date)::text AS score_date FROM quantrade.daily_research_runs WHERE status = 'completed' AND score_date < $1",
    [beforeDate],
  );
  const scoreDate = result.rows[0]?.score_date;
  return scoreDate ? { scoreDate, scores: await listDatedScores(scoreDate) } : null;
}

export async function getRecentScoreRuns(limit = 5): Promise<ScoreRunSummary[]> {
  const result = await databasePool().query(
    `SELECT score_date::text AS score_date, completed_at AS published_at,
            eligible_count
     FROM quantrade.daily_research_runs
     WHERE status = 'completed'
     ORDER BY score_date DESC
     LIMIT $1`,
    [limit],
  );
  return result.rows.map((row) => ({
    scoreDate: String(row.score_date),
    ...(row.published_at ? { publishedAt: new Date(String(row.published_at)).toISOString() } : {}),
    eligibleCount: Number(row.eligible_count),
  }));
}

export async function getTodayFilingActivity(scoreDate: string): Promise<TodayFilingActivity[]> {
  const result = await databasePool().query(
    `WITH daily_filings AS (
       SELECT f.security_id,
              COUNT(*)::int AS filing_count,
              ARRAY_AGG(DISTINCT f.form ORDER BY f.form) AS forms,
              MAX(f.accepted_at) AS latest_accepted_at
       FROM quantrade.filings f
       WHERE (f.accepted_at AT TIME ZONE 'America/Toronto')::date = $1::date
       GROUP BY f.security_id
     )
     SELECT daily_filings.security_id, s.issuer_name, l.ticker,
            daily_filings.filing_count, daily_filings.forms, daily_filings.latest_accepted_at
     FROM daily_filings
     JOIN quantrade.securities s ON s.security_id = daily_filings.security_id
     LEFT JOIN LATERAL (
       SELECT ticker
       FROM quantrade.listings
       WHERE security_id = daily_filings.security_id
         AND valid_from <= $1::date
         AND (valid_to IS NULL OR valid_to > $1::date)
       ORDER BY valid_from DESC
       LIMIT 1
     ) l ON TRUE
     ORDER BY daily_filings.latest_accepted_at DESC, l.ticker ASC NULLS LAST`,
    [scoreDate],
  );
  return result.rows.map((row) => ({
    securityId: String(row.security_id),
    issuerName: String(row.issuer_name),
    ticker: row.ticker ? String(row.ticker) : "Unavailable",
    filingCount: Number(row.filing_count),
    forms: Array.isArray(row.forms) ? row.forms.map(String) : [],
    latestAcceptedAt: new Date(String(row.latest_accepted_at)).toISOString(),
  }));
}

export async function getDailyOperationsStatus(): Promise<DailyOperationsStatus> {
  const [runResult, freshnessResult] = await Promise.all([
    databasePool().query(
      `SELECT score_date::text AS score_date, status, decision_at, completed_at,
              eligible_count, failure_reason
       FROM quantrade.daily_research_runs
       ORDER BY score_date DESC
       LIMIT 1`,
    ),
    databasePool().query(
      `SELECT
         (SELECT MAX(session_date)::text
          FROM quantrade.daily_price_bars
          WHERE session = 'regular' AND adjustment_basis = 'split_adjusted') AS market_session,
         (SELECT MAX(session_date)::text
          FROM quantrade.benchmark_daily_price_bars
          WHERE benchmark_ticker = 'SPY' AND session = 'regular'
            AND adjustment_basis = 'split_adjusted') AS benchmark_session,
         (SELECT MAX(retrieved_at)
          FROM quantrade.raw_artifacts
          WHERE provider = 'sec_edgar') AS sec_refresh_at`,
    ),
  ]);
  const run = runResult.rows[0] as Record<string, unknown> | undefined;
  const freshness = freshnessResult.rows[0] as Record<string, unknown> | undefined;
  return {
    ...(run ? {
      latestRun: {
        scoreDate: String(run.score_date),
        status: run.status as DailyOperationRunStatus,
        ...(run.decision_at ? { decisionAt: new Date(String(run.decision_at)).toISOString() } : {}),
        ...(run.completed_at ? { completedAt: new Date(String(run.completed_at)).toISOString() } : {}),
        ...(run.eligible_count === null ? {} : { eligibleCount: Number(run.eligible_count) }),
        ...(run.failure_reason ? { failureReason: String(run.failure_reason) } : {}),
      },
    } : {}),
    ...(freshness?.market_session ? { latestMarketSession: String(freshness.market_session) } : {}),
    ...(freshness?.benchmark_session ? { latestBenchmarkSession: String(freshness.benchmark_session) } : {}),
    ...(freshness?.sec_refresh_at ? { latestSecRefreshAt: new Date(String(freshness.sec_refresh_at)).toISOString() } : {}),
  };
}

export async function getForwardOutcomeReadiness(): Promise<ForwardOutcomeReadiness[]> {
  const result = await databasePool().query(
    `SELECT metric.horizon_sessions,
            metric.completed_labels,
            metric.withheld_labels,
            metric.pending_labels,
            metric.completed_score_dates,
            metric.latest_outcome_date::text AS latest_outcome_date
     FROM quantrade.forward_outcome_readiness_snapshots AS snapshot
     JOIN quantrade.forward_outcome_readiness_metrics AS metric
       ON metric.forward_outcome_readiness_snapshot_id = snapshot.forward_outcome_readiness_snapshot_id
     WHERE snapshot.as_of_date = (
       SELECT MAX(as_of_date) FROM quantrade.forward_outcome_readiness_snapshots
     )
     ORDER BY metric.horizon_sessions ASC`,
  );
  return result.rows.map((row) => ({
    horizonSessions: Number(row.horizon_sessions),
    completedLabels: Number(row.completed_labels),
    withheldLabels: Number(row.withheld_labels),
    pendingLabels: Number(row.pending_labels),
    completedScoreDates: Number(row.completed_score_dates),
    ...(row.latest_outcome_date ? { latestOutcomeDate: String(row.latest_outcome_date) } : {}),
  }));
}

export async function getLatestPaperPortfolio(): Promise<PaperPortfolio | null> {
  const result = await databasePool().query("SELECT paper_portfolio_run_id, score_date::text, execution_date::text, starting_nav FROM quantrade.paper_portfolio_runs ORDER BY score_date DESC LIMIT 1");
  if (!result.rowCount) return null;
  const row = result.rows[0] as Record<string, unknown>;
  const positions = await databasePool().query("SELECT p.security_id, p.quantity, s.issuer_name, l.ticker FROM quantrade.paper_portfolio_positions p JOIN quantrade.securities s ON s.security_id = p.security_id LEFT JOIN LATERAL (SELECT ticker FROM quantrade.listings WHERE security_id = p.security_id AND valid_to IS NULL ORDER BY valid_from DESC LIMIT 1) l ON TRUE WHERE p.paper_portfolio_run_id = $1 ORDER BY l.ticker", [row.paper_portfolio_run_id]);
  const outcomes = await databasePool().query(
    `SELECT horizon_sessions, status, outcome_date::text AS outcome_date,
            portfolio_return, benchmark_return, benchmark_relative_return, unavailable_reason
     FROM quantrade.paper_portfolio_outcomes
     WHERE paper_portfolio_run_id = $1
     ORDER BY horizon_sessions ASC`,
    [row.paper_portfolio_run_id],
  );
  return {
    scoreDate: String(row.score_date),
    executionDate: String(row.execution_date),
    startingNav: String(row.starting_nav),
    positions: positions.rows.map((item) => ({ securityId: String(item.security_id), ticker: item.ticker ? String(item.ticker) : "Unavailable", issuerName: String(item.issuer_name), quantity: String(item.quantity) })),
    outcomes: outcomes.rows.map((item) => ({
      horizonSessions: Number(item.horizon_sessions),
      status: item.status as PaperPortfolioOutcome["status"],
      outcomeDate: String(item.outcome_date),
      ...(item.portfolio_return === null ? {} : { portfolioReturn: String(item.portfolio_return) }),
      ...(item.benchmark_return === null ? {} : { benchmarkReturn: String(item.benchmark_return) }),
      ...(item.benchmark_relative_return === null ? {} : { benchmarkRelativeReturn: String(item.benchmark_relative_return) }),
      ...(item.unavailable_reason ? { unavailableReason: String(item.unavailable_reason) } : {}),
    })),
  };
}

export async function searchSecurities(query: string): Promise<SecuritySearchResult[]> {
  const term = query.trim();
  if (!term) {
    return [];
  }
  const result = await databasePool().query(
    `WITH current_listings AS (
       SELECT DISTINCT ON (security_id) security_id, ticker
       FROM quantrade.listings
       WHERE valid_to IS NULL
       ORDER BY security_id, valid_from DESC
     )
     SELECT s.security_id, s.issuer_name, l.ticker
     FROM quantrade.securities s
     JOIN current_listings l ON l.security_id = s.security_id
     WHERE l.ticker ILIKE $1 OR s.issuer_name ILIKE $1
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

export async function getLatestPriceSummaries(securityIds: string[]): Promise<LatestPriceSummary[]> {
  if (!securityIds.length) return [];
  const result = await databasePool().query(
    `WITH recent_prices AS (
       SELECT security_id, session_date, close_price,
              ROW_NUMBER() OVER (PARTITION BY security_id ORDER BY session_date DESC) AS position
       FROM quantrade.daily_price_bars
       WHERE security_id = ANY($1::uuid[])
         AND adjustment_basis = 'split_adjusted'
         AND session = 'regular'
     )
     SELECT security_id,
            MAX(session_date) FILTER (WHERE position = 1)::text AS session_date,
            MAX(close_price) FILTER (WHERE position = 1) AS close_price,
            MAX(close_price) FILTER (WHERE position = 2) AS previous_close_price
     FROM recent_prices
     WHERE position <= 2
     GROUP BY security_id
     ORDER BY security_id`,
    [securityIds],
  );
  return result.rows.map((row) => ({
    securityId: String(row.security_id),
    sessionDate: String(row.session_date),
    closePrice: String(row.close_price),
    ...(row.previous_close_price === null ? {} : { previousClosePrice: String(row.previous_close_price) }),
  }));
}

export async function getStockAtAGlance(securityId: string): Promise<StockAtAGlance | null> {
  const result = await databasePool().query(
    `WITH recent_prices AS (
       SELECT session_date, close_price,
              ROW_NUMBER() OVER (ORDER BY session_date DESC) AS position
       FROM quantrade.daily_price_bars
       WHERE security_id = $1
         AND adjustment_basis = 'split_adjusted'
         AND session = 'regular'
     ), latest_price AS (
       SELECT session_date, close_price FROM recent_prices WHERE position = 1
     ), previous_price AS (
       SELECT close_price FROM recent_prices WHERE position = 2
     )
     SELECT latest_price.session_date::text AS session_date,
            latest_price.close_price,
            previous_price.close_price AS previous_close_price,
            latest_price.close_price * shares.fact_value AS market_value,
            shares.period_end::text AS shares_reported_for
     FROM latest_price
     LEFT JOIN previous_price ON TRUE
     LEFT JOIN LATERAL (
       SELECT fact_value, period_end
       FROM quantrade.filing_facts
       WHERE security_id = $1
         AND taxonomy = 'dei'
         AND concept = 'EntityCommonStockSharesOutstanding'
         AND unit = 'shares'
       ORDER BY period_end DESC, available_at DESC
       LIMIT 1
     ) shares ON TRUE`,
    [securityId],
  );
  if (!result.rowCount) return null;
  const row = result.rows[0] as Record<string, unknown>;
  return {
    sessionDate: String(row.session_date),
    closePrice: String(row.close_price),
    ...(row.previous_close_price === null ? {} : { previousClosePrice: String(row.previous_close_price) }),
    ...(row.market_value === null ? {} : { marketValue: String(row.market_value) }),
    ...(row.shares_reported_for === null ? {} : { sharesReportedFor: String(row.shares_reported_for) }),
  };
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
     JOIN quantrade.daily_research_runs run
       ON run.score_date = s.score_date
      AND run.decision_at = s.decision_at
      AND run.status = 'completed'
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
