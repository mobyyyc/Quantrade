import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { formatResearchDate } from "@/lib/format";
import { getLatestDatedScores, getLatestPaperPortfolio, getModelCard, getRecentScoreRuns, ResearchReadModelError, type DatedScore, type ScoreRunSummary } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";

function coverageGate(reason?: string) {
  if (reason?.includes("EntityCommonStockSharesOutstanding")) return "Reported share count";
  if (reason?.includes("NetIncomeLoss") || reason?.includes("ProfitLoss")) return "Annual net income";
  if (reason?.toLowerCase().includes("asset")) return "Annual total assets";
  if (reason?.includes("completed split-adjusted sessions")) return "Price-history window";
  return "Other data-quality gate";
}

function coverageBreakdown(scores: DatedScore[]) {
  const withheld = scores.filter((score) => !score.eligible);
  return [...withheld.reduce((counts, score) => {
    const gate = coverageGate(score.unavailableReason);
    counts.set(gate, (counts.get(gate) ?? 0) + 1);
    return counts;
  }, new Map<string, number>())].sort(([, left], [, right]) => right - left);
}

export default async function ResearchPage() {
  let card = null;
  let portfolio = null;
  let latestScores = null;
  let recentRuns: ScoreRunSummary[] = [];
  let unavailable = false;
  try {
    card = await getModelCard("baseline_equal_weight_v1");
    portfolio = await getLatestPaperPortfolio();
    latestScores = await getLatestDatedScores();
    recentRuns = await getRecentScoreRuns();
  } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  const coverage = latestScores?.scores ?? [];
  const eligibleCount = coverage.filter((score) => score.eligible).length;
  const withheldCount = coverage.length - eligibleCount;
  const coveragePercent = coverage.length ? Math.round((eligibleCount / coverage.length) * 100) : 0;
  const gateBreakdown = coverageBreakdown(coverage).slice(0, 3);
  return <AppShell current="/research">
    <section className="page-intro compact"><p className="eyebrow">RESEARCH</p><h1>Know what the score can and cannot say.</h1><p className="lede">Quantrade turns dated quantitative evidence into a readable starting point for research.</p></section>
    <section className="content-section methodology"><div><p className="eyebrow">MODEL</p><h2>{card?.modelVersion ?? "Baseline research model"}</h2></div><div><p>{card?.purpose ?? "A transparent equal-weight reference that ranks only eligible research inputs."}</p><dl><div><dt>Status</dt><dd>{card?.status?.replaceAll("_", " ") ?? "Research-only"}</dd></div><div><dt>Data capability</dt><dd>Tier {card?.dataCapabilityTier ?? "B"}</dd></div><div><dt>Protocol</dt><dd>{card?.protocolVersion ?? "0.1"}</dd></div><div><dt>Latest score</dt><dd>{latestScores ? formatResearchDate(latestScores.scoreDate) : "Not published"}</dd></div></dl></div></section>
    <section className="content-section methodology"><div><p className="eyebrow">METHOD</p><h2>How a score is formed</h2></div><div><p>{card?.methodology ?? "Sector-aware feature percentiles are averaged only when every required input is available."}</p><Link href="/rankings" className="text-link">Open dated rankings</Link></div></section>
    <section className="content-section coverage-health"><div><p className="eyebrow">DATA COVERAGE</p><h2>What this run could score.</h2><p>Incomplete source data is withheld, never estimated or filled in.</p></div><div>{coverage.length ? <><p className="coverage-date">Latest completed run, {formatResearchDate(latestScores!.scoreDate)}</p><dl className="coverage-metrics"><div><dt>Eligible</dt><dd>{eligibleCount}</dd><span>published scores</span></div><div><dt>Withheld</dt><dd>{withheldCount}</dd><span>quality-gated names</span></div><div><dt>Coverage</dt><dd>{coveragePercent}%</dd><span>of this run</span></div></dl>{withheldCount ? <div className="coverage-gates"><p>Most common gates</p><ul>{gateBreakdown.map(([gate, count]) => <li key={gate}><span>{gate}</span><strong>{count} {count === 1 ? "name" : "names"}</strong></li>)}</ul></div> : <p className="coverage-complete">Every company in this run met the required data-quality gates.</p>}</> : <p className="quiet-copy">Coverage will appear after the first completed daily research run.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">RESEARCH ACTIVITY</p><h2>Recent score publications</h2></div><div>{recentRuns.length ? <ul className="publication-list">{recentRuns.map((run) => <li key={run.scoreDate}><strong>{formatResearchDate(run.scoreDate)}</strong><span>{run.eligibleCount} eligible names</span></li>)}</ul> : <p>No dated score publication has been recorded yet.</p>}</div></section>
    <section className="content-section methodology" id="track-record"><div><p className="eyebrow">TRACK RECORD</p><h2>Paper portfolio</h2></div><div>{portfolio ? <><p>A dated research basket, scored {formatResearchDate(portfolio.scoreDate)} and executed at the following regular-session open on {formatResearchDate(portfolio.executionDate)}.</p><dl><div><dt>Starting NAV</dt><dd>${Number(portfolio.startingNav).toLocaleString("en-CA")}</dd></div><div><dt>Positions</dt><dd>{portfolio.positions.length}</dd></div></dl></> : <p>No paper portfolio is published yet. This record appears only after an eligible score run can be executed under the documented next-session rule.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">LIMITS</p><h2>Read uncertainty plainly.</h2></div><div><ul className="plain-list">{card?.limitations?.map((limitation) => <li key={limitation}>{limitation}</li>) ?? <><li>Tier B data does not verify historical constituent or delisting coverage.</li><li>A research score is not investment advice, a prediction, or a guarantee.</li><li>Unavailable data blocks publication instead of being substituted.</li></>}</ul>{unavailable && <p className="inline-notice">The stored model card is unavailable until the research database is connected.</p>}</div></section>
  </AppShell>;
}
