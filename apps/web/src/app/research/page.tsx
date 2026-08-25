import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { formatPublicationTime, formatResearchDate } from "@/lib/format";
import { getForwardOutcomeReadiness, getLatestDatedScores, getLatestPaperPortfolio, getModelCard, getRecentScoreRuns, ML_DATASET_MINIMUM_COMPLETED_LABELS, ML_DATASET_MINIMUM_SCORE_DATES, ResearchReadModelError, type DatedScore, type ForwardOutcomeReadiness, type ScoreRunSummary } from "@/lib/research-read-model";

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

function formatReturn(value: string) {
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${(numeric * 100).toFixed(2)}%`;
}

export default async function ResearchPage() {
  let card = null;
  let portfolio = null;
  let latestScores = null;
  let recentRuns: ScoreRunSummary[] = [];
  let forwardReadiness: ForwardOutcomeReadiness[] = [];
  let unavailable = false;
  try {
    card = await getModelCard("baseline_equal_weight_v1");
    portfolio = await getLatestPaperPortfolio();
    latestScores = await getLatestDatedScores();
    recentRuns = await getRecentScoreRuns();
    forwardReadiness = await getForwardOutcomeReadiness();
  } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  const coverage = latestScores?.scores ?? [];
  const eligibleCount = coverage.filter((score) => score.eligible).length;
  const withheldCount = coverage.length - eligibleCount;
  const coveragePercent = coverage.length ? Math.round((eligibleCount / coverage.length) * 100) : 0;
  const gateBreakdown = coverageBreakdown(coverage).slice(0, 3);
  const latestResearch = coverage[0];
  const datasetReady = forwardReadiness.length === 3 && forwardReadiness.every((item) => item.completedLabels >= ML_DATASET_MINIMUM_COMPLETED_LABELS && item.completedScoreDates >= ML_DATASET_MINIMUM_SCORE_DATES);
  return <AppShell current="/research">
    <section className="page-intro compact"><p className="eyebrow">RESEARCH</p><h1>Know what the score can and cannot say.</h1><p className="lede">Quantrade turns dated quantitative evidence into a readable starting point for research.</p></section>
    <section className="content-section methodology"><div><p className="eyebrow">MODEL</p><h2>{latestResearch?.modelVersion ?? card?.modelVersion ?? "Baseline research model"}</h2></div><div><p>{card?.purpose ?? "A transparent equal-weight reference that ranks only eligible research inputs."}</p><dl><div><dt>Status</dt><dd>{card?.status?.replaceAll("_", " ") ?? "Research-only"}</dd></div><div><dt>Data capability</dt><dd>Tier {latestResearch?.dataCapabilityTier ?? card?.dataCapabilityTier ?? "B"}</dd></div><div><dt>Protocol</dt><dd>{latestResearch?.protocolVersion ?? card?.protocolVersion ?? "0.1"}</dd></div><div><dt>Research date</dt><dd>{latestScores ? formatResearchDate(latestScores.scoreDate) : "Not published"}</dd></div><div><dt>Data cutoff</dt><dd>{latestResearch ? formatPublicationTime(latestResearch.dataCutoffAt) : "Unavailable"}</dd></div><div><dt>Published</dt><dd>{latestResearch ? formatPublicationTime(latestResearch.publishedAt) : "Unavailable"}</dd></div></dl><p className="research-freshness-note">Each published result is tied to its recorded data cutoff and model configuration. Later market movement does not alter that dated research view.</p></div></section>
    <section className="content-section methodology"><div><p className="eyebrow">METHOD</p><h2>How a score is formed</h2></div><div><p>{card?.methodology ?? "Sector-aware feature percentiles are averaged only when every required input is available."}</p><Link href="/rankings" className="text-link">Open dated rankings</Link></div></section>
    <section className="content-section coverage-health"><div><p className="eyebrow">DATA COVERAGE</p><h2>What this run could score.</h2><p>Incomplete source data is withheld, never estimated or filled in.</p></div><div>{coverage.length ? <><p className="coverage-date">Latest completed run, {formatResearchDate(latestScores!.scoreDate)}</p><dl className="coverage-metrics"><div><dt>Eligible</dt><dd>{eligibleCount}</dd><span>published scores</span></div><div><dt>Withheld</dt><dd>{withheldCount}</dd><span>quality-gated names</span></div><div><dt>Coverage</dt><dd>{coveragePercent}%</dd><span>of this run</span></div></dl>{withheldCount ? <div className="coverage-gates"><p>Most common gates</p><ul>{gateBreakdown.map(([gate, count]) => <li key={gate}><span>{gate}</span><strong>{count} {count === 1 ? "name" : "names"}</strong></li>)}</ul></div> : <p className="coverage-complete">Every company in this run met the required data-quality gates.</p>}</> : <p className="quiet-copy">Coverage will appear after the first completed daily research run.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">RESEARCH ACTIVITY</p><h2>Recent score publications</h2></div><div>{recentRuns.length ? <ul className="publication-list">{recentRuns.map((run) => <li key={run.scoreDate}><strong>{formatResearchDate(run.scoreDate)}</strong><span>{run.eligibleCount} eligible names</span></li>)}</ul> : <p>No dated score publication has been recorded yet.</p>}</div></section>
    <section className="content-section methodology" id="track-record"><div><p className="eyebrow">TRACK RECORD</p><h2>Paper portfolio</h2></div><div>{portfolio ? <><p>A dated research basket, scored {formatResearchDate(portfolio.scoreDate)} and executed at the following regular-session open on {formatResearchDate(portfolio.executionDate)}.</p><dl><div><dt>Starting NAV</dt><dd>${Number(portfolio.startingNav).toLocaleString("en-CA")}</dd></div><div><dt>Positions</dt><dd>{portfolio.positions.length}</dd></div></dl><div className="portfolio-checkpoints"><p className="portfolio-checkpoints-title">Forward checkpoints</p><ul>{[5, 20, 60].map((horizon) => {
      const outcome = portfolio.outcomes.find((item) => item.horizonSessions === horizon);
      if (!outcome) return <li key={horizon}><strong>{horizon} sessions</strong><span>Awaiting its dated market close</span></li>;
      if (outcome.status === "withheld") return <li key={horizon}><strong>{horizon} sessions</strong><span>Withheld · {outcome.unavailableReason}</span></li>;
      const relative = Number(outcome.benchmarkRelativeReturn);
      return <li key={horizon}><strong>{horizon} sessions</strong><span className={relative >= 0 ? "positive-change" : "negative-change"}>{formatReturn(outcome.portfolioReturn!)} portfolio · {formatReturn(outcome.benchmarkRelativeReturn!)} vs SPY</span><small>{formatResearchDate(outcome.outcomeDate)}</small></li>;
    })}</ul><p className="portfolio-checkpoints-note">Each checkpoint uses the original next-open execution and its actual later market close. Missing marks or corporate actions are withheld, not estimated.</p></div></> : <p>No paper portfolio is published yet. This record appears only after an eligible score run can be executed under the documented next-session rule.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">ML FOUNDATION</p><h2>Future labels, tracked honestly.</h2></div><div>{forwardReadiness.length ? <><p>Each eligible score receives a future split-adjusted price-return label only after the relevant market window has closed. The minimum gate is {ML_DATASET_MINIMUM_COMPLETED_LABELS.toLocaleString("en-CA")} valid labels across {ML_DATASET_MINIMUM_SCORE_DATES} distinct research dates for every horizon.</p><dl className="ml-readiness-list">{forwardReadiness.map((item) => <div key={item.horizonSessions}><dt>{item.horizonSessions}-session label</dt><dd>{item.completedLabels.toLocaleString("en-CA")}</dd><span>completed labels · {item.completedScoreDates}/{ML_DATASET_MINIMUM_SCORE_DATES} research dates</span><small>{item.withheldLabels.toLocaleString("en-CA")} withheld · {item.pendingLabels.toLocaleString("en-CA")} awaiting</small>{item.latestOutcomeDate && <time dateTime={item.latestOutcomeDate}>Latest: {formatResearchDate(item.latestOutcomeDate)}</time>}</div>)}</dl><p className="ml-readiness-note">{datasetReady ? "Dataset minimum met. Model work may begin only with the existing walk-forward and holdout controls." : "Collection is in progress. No ML model will be trained or presented until every horizon meets this minimum."}</p></> : <p className="quiet-copy">Forward-label readiness will appear after the research database is connected.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">LIMITS</p><h2>Read uncertainty plainly.</h2></div><div><ul className="plain-list">{card?.limitations?.map((limitation) => <li key={limitation}>{limitation}</li>) ?? <><li>Tier B data does not verify historical constituent or delisting coverage.</li><li>A research score is not investment advice, a prediction, or a guarantee.</li><li>Unavailable data blocks publication instead of being substituted.</li></>}</ul>{unavailable && <p className="inline-notice">The stored model card is unavailable until the research database is connected.</p>}</div></section>
  </AppShell>;
}
