import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { formatPercentile, formatResearchDate, formatScore } from "@/lib/format";
import { getDatedScore, getLatestDatedScores, getScoreExplanations, getSecurityIdentity, ResearchReadModelError, type DatedScore, type ScoreExplanation, type SecuritySearchResult } from "@/lib/research-read-model";

export default async function StockDetailPage({ params, searchParams }: { params: Promise<{ securityId: string }>; searchParams: Promise<{ date?: string }> }) {
  const { securityId } = await params;
  const { date } = await searchParams;
  let identity: SecuritySearchResult | null = null;
  let score: DatedScore | null = null;
  let explanations: ScoreExplanation[] = [];
  let unavailable = false;
  try {
    identity = await getSecurityIdentity(securityId);
    const scoreDate = date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : (await getLatestDatedScores())?.scoreDate;
    if (scoreDate) {
      score = await getDatedScore(securityId, scoreDate);
      if (score) explanations = await getScoreExplanations(securityId, scoreDate);
    }
  } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  const title = identity ? `${identity.ticker} · ${identity.issuerName}` : "Research detail";
  return <AppShell current="">
    <section className="detail-header"><Link href="/rankings" className="back-link">← Rankings</Link><p className="eyebrow">STOCK DETAIL</p><h1>{title}</h1>{score ? <p className="lede">Research score for {formatResearchDate(score.scoreDate)}. It is a dated research view, not a trade instruction.</p> : <p className="lede">Open a dated score to review model evidence and limits.</p>}</section>
    {score ? <>
      <section className="detail-score"><div><p className="eyebrow">RESEARCH SCORE</p><p className="anchor-score">{formatScore(score.score)}<span>/100</span></p><p className="quiet-copy">Rank {score.rank ?? "Unavailable"} · {score.signal} · Tier {score.dataCapabilityTier}</p></div><div className="detail-context"><span>Data cutoff</span><strong>{new Date(score.dataCutoffAt).toLocaleString("en-CA", { timeZone: "America/Toronto" })}</strong><span>Model</span><strong>{score.modelVersion}</strong></div></section>
      <section className="content-section"><div className="section-heading"><div><p className="eyebrow">WHY IT APPEARS</p><h2>Feature evidence</h2></div><span className="status-label">{explanations.length} inputs</span></div>{explanations.length ? <ul className="evidence-list">{explanations.slice(0, 3).map((item) => <li key={`${item.featureKey}-${item.featureVersion}`}><div><strong>{item.displayName ?? item.featureKey}</strong><span>{formatPercentile(item.percentile)} in {item.sectorCode}</span></div><p>{item.contribution ? `${Math.round(Number(item.contribution) * 100)} score points from a fixed equal weight.` : `Not available: ${item.unavailableReason ?? "missing research input"}`}</p></li>)}</ul> : <p className="empty-inline">Feature explanations are not available for this dated score.</p>}</section>
      <section className="content-section split-note"><div><p className="eyebrow">WHAT TO VERIFY</p><h2>Risk and freshness matter.</h2></div><p>Review data freshness, Tier B limitations, and the underlying methodology before using this research as a starting point for further investigation.</p></section>
      <section className="content-section chart-placeholder"><div><p className="eyebrow">PRICE CONTEXT</p><h2>Price context is not published yet.</h2></div><p>A dated chart will appear only when normalized price history is available through the product read model. No illustrative price line is substituted.</p></section>
    </> : <section className="empty-state"><p className="eyebrow">RESEARCH STATUS</p><h2>{unavailable ? "Research data is not connected." : "No dated score is available for this company."}</h2><p>{unavailable ? "Connect the normalized research database to load company identity, score evidence, and model context." : "Try another published score date from Rankings, or return to Search."}</p><Link href="/search" className="primary-link">Search companies</Link></section>}
  </AppShell>;
}
