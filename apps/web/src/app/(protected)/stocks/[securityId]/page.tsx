import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PriceChart } from "@/components/price-chart";
import { ScoreHistory } from "@/components/score-history";
import { WatchlistButton } from "@/components/watchlist-button";
import { formatCompactUsd, formatPercentile, formatPriceChange, formatPublicationTime, formatResearchDate, formatScore, formatUsdPrice } from "@/lib/format";
import { getDailyPriceHistory, getDatedScore, getLatestDatedScores, getModelCard, getScoreExplanations, getScoreHistory, getSecurityIdentity, getStockAtAGlance, ResearchReadModelError, type DailyPricePoint, type DatedScore, type ModelCard, type ScoreExplanation, type ScoreHistoryPoint, type SecuritySearchResult, type StockAtAGlance } from "@/lib/research-read-model";

function unavailableScoreSummary(reason?: string) {
  if (reason?.includes("EntityCommonStockSharesOutstanding")) return "A current SEC-reported share count is unavailable.";
  if (reason?.includes("NetIncomeLoss") || reason?.includes("ProfitLoss")) return "An eligible annual SEC net-income fact is unavailable.";
  if (reason?.toLowerCase().includes("asset")) return "An eligible annual SEC assets fact is unavailable.";
  if (reason?.includes("completed split-adjusted sessions")) return "The required price-history window has not accumulated yet.";
  return "One or more required research inputs did not pass the data-quality gate.";
}

function unavailableInputSummary(reason?: string) {
  if (reason?.includes("completed split-adjusted sessions")) return "Required price-history window is incomplete.";
  if (reason?.toLowerCase().includes("formation") || reason?.toLowerCase().includes("close")) return "The formation-date market bar is unavailable.";
  return "This input did not pass its data-quality gate.";
}

export default async function StockDetailPage({ params, searchParams }: { params: Promise<{ securityId: string }>; searchParams: Promise<{ date?: string; from?: string }> }) {
  const { securityId } = await params;
  const { date, from } = await searchParams;
  let identity: SecuritySearchResult | null = null;
  let score: DatedScore | null = null;
  let modelCard: ModelCard | null = null;
  let explanations: ScoreExplanation[] = [];
  let scoreHistory: ScoreHistoryPoint[] = [];
  let priceHistory: DailyPricePoint[] = [];
  let marketSnapshot: StockAtAGlance | null = null;
  let unavailable = false;
  try {
    identity = await getSecurityIdentity(securityId);
    if (identity) [priceHistory, marketSnapshot] = await Promise.all([getDailyPriceHistory(securityId), getStockAtAGlance(securityId)]);
    const scoreDate = date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : (await getLatestDatedScores())?.scoreDate;
    if (scoreDate) {
      [score, scoreHistory] = await Promise.all([getDatedScore(securityId, scoreDate), getScoreHistory(securityId, scoreDate)]);
      if (score) [explanations, modelCard] = await Promise.all([
        getScoreExplanations(score.scoreSnapshotId),
        getModelCard(score.modelVersion),
      ]);
    }
  } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  const returnTo = from === "today" ? "/" : from === "watchlist" ? "/watchlist" : from === "rankings" ? "/rankings" : from === "portfolio" ? "/portfolio" : "/search";
  const returnLabel = from === "today" ? "Today" : from === "watchlist" ? "Watchlist" : from === "rankings" ? "Rankings" : from === "portfolio" ? "Portfolio" : "Search";
  const factorContext: Record<string, string> = {
    momentum_12_1: "Price strength over the prior year, excluding the most recent month.",
    relative_strength_6m: "Six-month price strength relative to the benchmark.",
    earnings_yield_ttm: "Reported earnings relative to the current market value.",
    return_on_assets_ttm: "Reported profitability relative to the company’s assets.",
    trailing_volatility_60d: "Recent price variability, where lower risk ranks better.",
    median_dollar_volume_20d: "Typical recent trading liquidity.",
  };
  const factorDisplayNames: Record<string, string> = {
    momentum_12_1: "12–1 month momentum",
    relative_strength_6m: "Six-month relative strength",
    earnings_yield_ttm: "Trailing earnings yield",
    return_on_assets_ttm: "Trailing return on assets",
    trailing_volatility_60d: "60-day volatility",
    median_dollar_volume_20d: "20-day trading liquidity",
  };
  const normalizedFeatureKey = (key: string) => key.replace(/_percentile$/, "");
  const explainedInputs = explanations.filter((item) => item.contribution !== undefined);
  const registeredInputs = modelCard?.inputs ?? [];
  const activeInputs = registeredInputs.filter((item) => item.active);
  const zeroWeightInputs = registeredInputs.filter((item) => !item.active);
  const exactZeroEligibility = score?.protocolVersion === "score_snapshot_exact_zero_v1";
  const requiredInputCount = registeredInputs.length
    ? (exactZeroEligibility ? activeInputs.length : registeredInputs.length)
    : explainedInputs.length;
  const supports = [...explainedInputs]
    .filter((item) => Number(item.contribution) > 0)
    .sort((left, right) => Number(right.contribution) - Number(left.contribution));
  const headwinds = [...explainedInputs]
    .filter((item) => Number(item.contribution) < 0)
    .sort((left, right) => Number(left.contribution) - Number(right.contribution));
  const neutralInputs = explainedInputs.filter((item) => Number(item.contribution) === 0);
  const activeInputStatuses = activeInputs.map((input) => ({
    input,
    explanation: explanations.find((item) => normalizedFeatureKey(item.featureKey) === input.featureKey),
  }));
  const evidenceCopy = (item: ScoreExplanation) => factorContext[normalizedFeatureKey(item.featureKey)] ?? "A current model input.";
  const evidenceName = (item: ScoreExplanation) => item.displayName ?? factorDisplayNames[normalizedFeatureKey(item.featureKey)] ?? normalizedFeatureKey(item.featureKey);
  const priceChange = marketSnapshot ? formatPriceChange(marketSnapshot.closePrice, marketSnapshot.previousClosePrice) : null;
  const eligibleScore = score?.eligible ? score : null;
  return <AppShell current="">
    <section className="detail-header"><Link href={returnTo} className="back-link">← {returnLabel}</Link><div className="detail-heading-row"><div><p className="eyebrow">STOCK DETAIL</p>{identity ? <h1 className="stock-identity"><span className="stock-ticker">{identity.ticker}</span><span className="stock-company-name">{identity.issuerName}</span></h1> : <h1>Research detail</h1>}</div>{identity && <WatchlistButton company={identity} />}</div>{eligibleScore ? <p className="lede">Research score for {formatResearchDate(eligibleScore.scoreDate)}. It is a dated research view, not a trade instruction.</p> : <p className="lede">Real daily price history is available. A full research score will publish only after every required input passes its data-quality gate.</p>}</section>
    {eligibleScore ? <>
      <section className="detail-snapshot" aria-label="Research and price context"><section className="detail-score"><div><p className="eyebrow">RESEARCH SCORE</p><p className="anchor-score">{formatScore(eligibleScore.score)}<span>/100</span></p><p className="quiet-copy">Rank {eligibleScore.rank ?? "Unavailable"} · {eligibleScore.signal} · Tier {eligibleScore.dataCapabilityTier}</p></div><div className="detail-context"><div><span>Data cutoff</span><strong>{formatPublicationTime(eligibleScore.dataCutoffAt)}</strong></div><div><span>Published</span><strong>{formatPublicationTime(eligibleScore.publishedAt)}</strong></div><div><span>Model</span><strong>{eligibleScore.modelVersion}</strong></div></div></section>{identity && <PriceChart points={priceHistory} ticker={identity.ticker} />}</section>
      {marketSnapshot && <section className="stock-overview" aria-label="Market facts"><div className="stock-overview-item"><span>Market value</span><strong>{marketSnapshot.marketValue ? formatCompactUsd(marketSnapshot.marketValue) : "Unavailable"}</strong><small>{marketSnapshot.sharesReportedFor ? `Based on shares reported ${formatResearchDate(marketSnapshot.sharesReportedFor)}` : "Reported share count unavailable"}</small></div><div className="stock-overview-item"><span>Shares basis</span><strong>{marketSnapshot.sharesReportedFor ? "Reported" : "Unavailable"}</strong><small>{marketSnapshot.sharesReportedFor ? `Most recent filing, ${formatResearchDate(marketSnapshot.sharesReportedFor)}` : "No current SEC share-count fact"}</small></div><div className="stock-overview-item"><span>Market session</span><strong>{formatResearchDate(marketSnapshot.sessionDate)}</strong><small>Latest regular-session close</small></div></section>}
      <ScoreHistory points={scoreHistory} />
      <section className="content-section">
        <div className="section-heading score-input-heading">
          <div><p className="eyebrow">WHY THIS SCORE</p><h2>What influenced it</h2></div>
          <dl className="score-input-summary" aria-label="Model input summary">
            <div><dt>Active</dt><dd>{activeInputs.length || explainedInputs.length}<small>determine rank</small></dd></div>
            <div><dt>Registered</dt><dd>{registeredInputs.length || explainedInputs.length}<small>model schema</small></dd></div>
            <div><dt>Displayed</dt><dd>{explainedInputs.length}<small>dated evidence</small></dd></div>
            <div><dt>Required for run</dt><dd>{requiredInputCount}<small>publication gate</small></dd></div>
          </dl>
        </div>
        {explainedInputs.length ? <>
          <p className="evidence-intro">{registeredInputs.length
            ? exactZeroEligibility
              ? `${activeInputs.length} active inputs determine rank. ${zeroWeightInputs.length} zero-weight inputs remain registered for lineage, but do not affect this score or its eligibility.`
              : `${activeInputs.length} active inputs determine rank. This dated publication required all ${registeredInputs.length} registered inputs, although ${zeroWeightInputs.length} zero-weight inputs did not change the score.`
            : "The model compares each active input with companies in the same sector. These are the clearest current influences, not a prediction or trade instruction."}</p>
          <div className="evidence-groups">
            <section className="evidence-group" aria-labelledby="supports-score"><div className="evidence-group-heading"><h3 id="supports-score">Supports the score</h3><span>Positive contribution</span></div>{supports.length ? <ul className="evidence-list">{supports.map((item) => <li key={`${item.featureKey}-${item.featureVersion}`}><div><strong>{evidenceName(item)}</strong><span>{formatPercentile(item.percentile)} among {item.sectorCode} peers</span></div><p>{evidenceCopy(item)}</p></li>)}</ul> : <p className="evidence-empty">No active input is currently lifting this score.</p>}</section>
            <section className="evidence-group" aria-labelledby="headwinds-score"><div className="evidence-group-heading"><h3 id="headwinds-score">Worth watching</h3><span>Negative contribution</span></div>{headwinds.length ? <ul className="evidence-list">{headwinds.map((item) => <li key={`${item.featureKey}-${item.featureVersion}`}><div><strong>{evidenceName(item)}</strong><span>{formatPercentile(item.percentile)} among {item.sectorCode} peers</span></div><p>{evidenceCopy(item)}</p></li>)}</ul> : <p className="evidence-empty">No active input is currently holding this score back.</p>}</section>
            {neutralInputs.length > 0 && <section className="evidence-group evidence-group-wide" aria-labelledby="neutral-score"><div className="evidence-group-heading"><h3 id="neutral-score">Neutral in this score</h3><span>Zero contribution for this company</span></div><ul className="evidence-list">{neutralInputs.map((item) => <li key={`${item.featureKey}-${item.featureVersion}`}><div><strong>{evidenceName(item)}</strong><span>{formatPercentile(item.percentile)} among {item.sectorCode} peers</span></div><p>{evidenceCopy(item)}</p></li>)}</ul></section>}
          </div>
        </> : <p className="empty-inline">Feature explanations are not available for this dated score.</p>}
        {registeredInputs.length > 0 && <details className="model-input-disclosure">
          <summary>View all {registeredInputs.length} registered model inputs</summary>
          <ul>{registeredInputs.map((input) => <li key={input.modelColumn}><div><strong>{input.displayName}</strong><span>{input.featureKey} · {input.featureVersion}</span></div><span>{input.active ? "Active · affects rank" : "Zero weight · does not affect score"}</span></li>)}</ul>
        </details>}
      </section>
      <section className="content-section split-note"><div><p className="eyebrow">WHAT TO VERIFY</p><h2>Risk and freshness matter.</h2></div><p>Review data freshness, Tier B limitations, and the underlying methodology before using this research as a starting point for further investigation.</p></section>
    </> : <>{identity && <PriceChart points={priceHistory} ticker={identity.ticker} />}{marketSnapshot && <section className="stock-overview" aria-label="Market facts"><div className="stock-overview-item"><span>Latest close</span><strong>{formatUsdPrice(marketSnapshot.closePrice)}</strong>{priceChange ? <small className={priceChange.direction === "positive" ? "positive-change" : "negative-change"}>{priceChange.percent} since prior close</small> : <small>{formatResearchDate(marketSnapshot.sessionDate)} close</small>}</div><div className="stock-overview-item"><span>Market value</span><strong>{marketSnapshot.marketValue ? formatCompactUsd(marketSnapshot.marketValue) : "Unavailable"}</strong><small>{marketSnapshot.sharesReportedFor ? `Based on shares reported ${formatResearchDate(marketSnapshot.sharesReportedFor)}` : "Reported share count unavailable"}</small></div><div className="stock-overview-item"><span>Market session</span><strong>{formatResearchDate(marketSnapshot.sessionDate)}</strong><small>Latest regular-session close</small></div></section>}{score ? <><section className="unavailable-score"><div><p className="eyebrow">RESEARCH STATUS</p><h2>A score is not available for this run.</h2><p>{unavailableScoreSummary(score.unavailableReason)} Quantrade does not estimate a score when source data is incomplete.</p></div><dl><div><dt>Checked</dt><dd>{formatResearchDate(score.scoreDate)}</dd></div><div><dt>Model</dt><dd>{score.modelVersion}</dd></div><div><dt>Result</dt><dd>Withheld</dd></div></dl><Link href="/research" className="text-link">Read methodology</Link></section>{activeInputStatuses.length > 0 && <section className="content-section input-availability"><div><p className="eyebrow">ACTIVE INPUT STATUS</p><h2>What passed the publication gate.</h2></div><ul>{activeInputStatuses.map(({ input, explanation }) => <li key={input.modelColumn}><div><strong>{input.displayName}</strong><span>{input.featureKey} · {input.featureVersion}</span></div><div><strong>{explanation?.unavailableReason || explanation?.percentile === undefined ? "Unavailable" : "Available"}</strong>{explanation?.unavailableReason && <span>{unavailableInputSummary(explanation.unavailableReason)}</span>}</div></li>)}</ul></section>}</> : <section className="empty-state small"><p className="eyebrow">RESEARCH STATUS</p><h2>{unavailable ? "Research data is not connected." : "No dated score is available yet."}</h2><p>{unavailable ? "Connect the normalized research database to load company identity, price history, score evidence, and model context." : "The score pipeline will publish only when market, fundamental, and sector inputs are complete. The chart above uses the real normalized daily price history already available."}</p><Link href="/search" className="primary-link">Search another company</Link></section>}</>}
  </AppShell>;
}
