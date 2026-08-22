import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PriceChart } from "@/components/price-chart";
import { WatchlistButton } from "@/components/watchlist-button";
import { formatPercentile, formatResearchDate, formatScore } from "@/lib/format";
import { getDailyPriceHistory, getDatedScore, getLatestDatedScores, getScoreExplanations, getSecurityIdentity, ResearchReadModelError, type DailyPricePoint, type DatedScore, type ScoreExplanation, type SecuritySearchResult } from "@/lib/research-read-model";

export default async function StockDetailPage({ params, searchParams }: { params: Promise<{ securityId: string }>; searchParams: Promise<{ date?: string; from?: string }> }) {
  const { securityId } = await params;
  const { date, from } = await searchParams;
  let identity: SecuritySearchResult | null = null;
  let score: DatedScore | null = null;
  let explanations: ScoreExplanation[] = [];
  let priceHistory: DailyPricePoint[] = [];
  let unavailable = false;
  try {
    identity = await getSecurityIdentity(securityId);
    if (identity) priceHistory = await getDailyPriceHistory(securityId);
    const scoreDate = date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : (await getLatestDatedScores())?.scoreDate;
    if (scoreDate) {
      score = await getDatedScore(securityId, scoreDate);
      if (score) explanations = await getScoreExplanations(securityId, scoreDate);
    }
  } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  const returnTo = from === "today" ? "/" : from === "watchlist" ? "/watchlist" : from === "rankings" ? "/rankings" : "/search";
  const returnLabel = from === "today" ? "Today" : from === "watchlist" ? "Watchlist" : from === "rankings" ? "Rankings" : "Search";
  const factorContext: Record<string, string> = {
    momentum_12_1: "Price strength over the prior year, excluding the most recent month.",
    relative_strength_6m: "Six-month price strength relative to the benchmark.",
    earnings_yield_ttm: "Reported earnings relative to the current market value.",
    return_on_assets_ttm: "Reported profitability relative to the company’s assets.",
    trailing_volatility_60d: "Recent price variability, where lower risk ranks better.",
    median_dollar_volume_20d: "Typical recent trading liquidity.",
  };
  return <AppShell current="">
    <section className="detail-header"><Link href={returnTo} className="back-link">← {returnLabel}</Link><div className="detail-heading-row"><div><p className="eyebrow">STOCK DETAIL</p>{identity ? <h1 className="stock-identity"><span className="stock-ticker">{identity.ticker}</span><span className="stock-company-name">{identity.issuerName}</span></h1> : <h1>Research detail</h1>}</div>{identity && <WatchlistButton company={identity} />}</div>{score ? <p className="lede">Research score for {formatResearchDate(score.scoreDate)}. It is a dated research view, not a trade instruction.</p> : <p className="lede">Real daily price history is available. A full research score will publish only after every required input passes its data-quality gate.</p>}</section>
    {identity && <PriceChart points={priceHistory} ticker={identity.ticker} />}
    {score ? <>
      <section className="detail-score"><div><p className="eyebrow">RESEARCH SCORE</p><p className="anchor-score">{formatScore(score.score)}<span>/100</span></p><p className="quiet-copy">Rank {score.rank ?? "Unavailable"} · {score.signal} · Tier {score.dataCapabilityTier}</p></div><div className="detail-context"><span>Data cutoff</span><strong>{new Date(score.dataCutoffAt).toLocaleString("en-CA", { timeZone: "America/Toronto" })}</strong><span>Model</span><strong>{score.modelVersion}</strong></div></section>
      <section className="content-section"><div className="section-heading"><div><p className="eyebrow">WHY IT APPEARS</p><h2>Feature evidence</h2></div><span className="status-label">{explanations.length} inputs</span></div>{explanations.length ? <ul className="evidence-list">{explanations.slice(0, 3).map((item) => <li key={`${item.featureKey}-${item.featureVersion}`}><div><strong>{item.displayName ?? item.featureKey}</strong><span>{formatPercentile(item.percentile)} in {item.sectorCode}</span></div><p>{item.contribution ? <>{factorContext[item.featureKey] ?? "A dated model input."} {Math.round(Number(item.contribution) * 100)} score points from the fixed equal weight.</> : `Not available: ${item.unavailableReason ?? "missing research input"}`}</p></li>)}</ul> : <p className="empty-inline">Feature explanations are not available for this dated score.</p>}</section>
      <section className="content-section split-note"><div><p className="eyebrow">WHAT TO VERIFY</p><h2>Risk and freshness matter.</h2></div><p>Review data freshness, Tier B limitations, and the underlying methodology before using this research as a starting point for further investigation.</p></section>
    </> : <section className="empty-state small"><p className="eyebrow">RESEARCH STATUS</p><h2>{unavailable ? "Research data is not connected." : "No dated score is available yet."}</h2><p>{unavailable ? "Connect the normalized research database to load company identity, price history, score evidence, and model context." : "The score pipeline will publish only when market, fundamental, and sector inputs are complete. The chart above uses the real normalized daily price history already available."}</p><Link href="/search" className="primary-link">Search another company</Link></section>}
  </AppShell>;
}
