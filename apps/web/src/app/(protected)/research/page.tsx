import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { formatPercentagePoints, formatPublicationTime, formatResearchDate } from "@/lib/format";
import { operationStateLabel, publicationFreshnessLabel } from "@/lib/daily-update-state";
import { getActiveModelCard, getActivePredictionContext, getDailyOperationsHistory, getDailyOperationsStatus, getForwardOutcomeReadiness, getLatestDatedScores, getLatestModelHealth, getLatestPaperPortfolio, getRecentScoreRuns, ML_DATASET_MINIMUM_COMPLETED_LABELS, ML_DATASET_MINIMUM_SCORE_DATES, ResearchReadModelError, type DailyOperationHistoryEntry, type DailyOperationsStatus, type DatedScore, type ForwardOutcomeReadiness, type ModelHealthSnapshot, type PredictionContext, type ScoreRunSummary } from "@/lib/research-read-model";

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

function formatRatio(value?: string) {
  return value === undefined ? "Insufficient history" : `${(Number(value) * 100).toFixed(1)}%`;
}

function readableMetric(value: string) {
  return value.replaceAll("_", " ");
}

function nextScheduledUpdate() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Toronto", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date()).reduce<Record<string, string>>((values, part) => ({ ...values, [part.type]: part.value }), {});
  const candidate = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day)));
  if (Number(parts.hour) > 22 || (Number(parts.hour) === 22 && Number(parts.minute) >= 15)) candidate.setUTCDate(candidate.getUTCDate() + 1);
  while (candidate.getUTCDay() === 0 || candidate.getUTCDay() === 6) candidate.setUTCDate(candidate.getUTCDate() + 1);
  return `${formatResearchDate(candidate.toISOString().slice(0, 10))}, 10:15 PM Toronto`;
}

function runHistoryNote(run: DailyOperationHistoryEntry) {
  const notes: string[] = [];
  if (run.attemptCount > 1) notes.push(`${run.attemptCount} attempts`);
  if (run.providerRetryCount) notes.push(`${run.providerRetryCount} provider ${run.providerRetryCount === 1 ? "retry" : "retries"}`);
  if (run.duplicatePreventedCount) notes.push(`${run.duplicatePreventedCount} duplicate ${run.duplicatePreventedCount === 1 ? "blocked" : "attempts blocked"}`);
  if (run.warningCount) notes.push(`${run.warningCount} post-publication ${run.warningCount === 1 ? "warning" : "warnings"}`);
  if (!notes.length && run.state === "complete") notes.push("Completed without retry");
  if (!notes.length && run.state === "skipped") notes.push("No market session to publish");
  if (!notes.length && run.state === "failed") notes.push("Stopped safely before publication");
  if (!notes.length && run.state === "partial") notes.push("Published scores; maintenance needs a retry");
  if (!notes.length && run.state === "retrying") notes.push("Provider retry is in progress");
  if (!notes.length && run.state === "duplicate_prevented") notes.push("Existing publication reused safely");
  if (!notes.length) notes.push("Update is in progress");
  return notes.join(" · ");
}

export default async function ResearchPage() {
  let card = null;
  let portfolio = null;
  let latestScores = null;
  let recentRuns: ScoreRunSummary[] = [];
  let forwardReadiness: ForwardOutcomeReadiness[] = [];
  let operations: DailyOperationsStatus = { publicationFreshness: "unavailable" };
  let operationsHistory: DailyOperationHistoryEntry[] = [];
  let predictionContext: PredictionContext | null = null;
  let modelHealth: ModelHealthSnapshot | null = null;
  let unavailable = false;
  try {
    [card, portfolio, latestScores, recentRuns, forwardReadiness, operations, operationsHistory, predictionContext, modelHealth] = await Promise.all([
      getActiveModelCard(),
      getLatestPaperPortfolio(),
      getLatestDatedScores(),
      getRecentScoreRuns(),
      getForwardOutcomeReadiness(),
      getDailyOperationsStatus(),
      getDailyOperationsHistory(),
      getActivePredictionContext(),
      getLatestModelHealth(),
    ]);
  } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  const coverage = latestScores?.scores ?? [];
  const eligibleCount = coverage.filter((score) => score.eligible).length;
  const withheldCount = coverage.length - eligibleCount;
  const coveragePercent = coverage.length ? Math.round((eligibleCount / coverage.length) * 100) : 0;
  const gateBreakdown = coverageBreakdown(coverage).slice(0, 3);
  const latestResearch = coverage[0];
  const registeredInputCount = card?.inputs.length ?? 0;
  const activeInputCount = card?.inputs.filter((input) => input.active).length ?? 0;
  const zeroWeightInputCount = registeredInputCount - activeInputCount;
  const latestUsesExactZeroEligibility = latestResearch?.protocolVersion === "score_snapshot_exact_zero_v1";
  const datasetReady = forwardReadiness.length === 3 && forwardReadiness.every((item) => item.completedLabels >= ML_DATASET_MINIMUM_COMPLETED_LABELS && item.completedScoreDates >= ML_DATASET_MINIMUM_SCORE_DATES);
  return <AppShell current="/research">
    <section className="page-intro compact"><p className="eyebrow">RESEARCH</p><h1>Know what the score can and cannot say.</h1><p className="lede">Quantrade turns dated quantitative evidence into a readable starting point for research.</p></section>
    <section className="content-section methodology"><div><p className="eyebrow">MODEL</p><h2>{latestResearch?.modelVersion ?? card?.modelVersion ?? "Baseline research model"}</h2></div><div><p>{card?.purpose ?? "A transparent equal-weight reference that ranks only eligible research inputs."}</p><dl><div><dt>Status</dt><dd>{card?.status?.replaceAll("_", " ") ?? "Research-only"}</dd></div><div><dt>Data capability</dt><dd>Tier {latestResearch?.dataCapabilityTier ?? card?.dataCapabilityTier ?? "B"}</dd></div><div><dt>Protocol</dt><dd>{latestResearch?.protocolVersion ?? card?.protocolVersion ?? "0.1"}</dd></div><div><dt>Research date</dt><dd>{latestScores ? formatResearchDate(latestScores.scoreDate) : "Not published"}</dd></div><div><dt>Data cutoff</dt><dd>{latestResearch ? formatPublicationTime(latestResearch.dataCutoffAt) : "Unavailable"}</dd></div><div><dt>Published</dt><dd>{latestResearch ? formatPublicationTime(latestResearch.publishedAt) : "Unavailable"}</dd></div></dl><p className="research-freshness-note">Each published result is tied to its recorded data cutoff and model configuration. Later market movement does not alter that dated research view.</p></div></section>
    <section className="content-section methodology model-input-method"><div><p className="eyebrow">MODEL INPUTS</p><h2>Separate influence from lineage.</h2></div><div>{registeredInputCount ? <><p>{activeInputCount} active inputs have non-zero coefficients and determine score and rank. {zeroWeightInputCount} zero-weight inputs remain registered so the deployed artifact can be audited, but they do not change the score.</p><dl><div><dt>Registered</dt><dd>{registeredInputCount}</dd></div><div><dt>Active</dt><dd>{activeInputCount}</dd></div><div><dt>Zero weight</dt><dd>{zeroWeightInputCount}</dd></div></dl><p className="research-freshness-note">{latestUsesExactZeroEligibility ? `This dated protocol requires the ${activeInputCount} active inputs for publication.` : `This dated legacy protocol required all ${registeredInputCount} registered inputs for publication, including zero-weight inputs.`}</p><details className="model-input-disclosure"><summary>View registered input lineage</summary><ul>{card!.inputs.map((input) => <li key={input.modelColumn}><div><strong>{input.displayName}</strong><span>{input.featureKey} · {input.featureVersion}</span></div><span>{input.active ? "Active · affects rank" : "Zero weight · does not affect score"}</span></li>)}</ul></details></> : <p className="quiet-copy">Input lineage is unavailable until the active artifact contract is registered.</p>}</div></section>
    <section className="content-section model-health"><div><p className="eyebrow">MODEL HEALTH</p><h2>{modelHealth ? `${modelHealth.status[0].toUpperCase()}${modelHealth.status.slice(1)} for ${formatResearchDate(modelHealth.scoreDate)}.` : "Awaiting the first health snapshot."}</h2><p>Monitoring records evidence and warnings. It never retrains or promotes a model automatically.</p></div>{modelHealth ? <div><dl className="model-health-summary"><div><dt>Coverage</dt><dd>{formatRatio(modelHealth.coverageRatio)}<span>{modelHealth.eligibleCount} of {modelHealth.cohortSize}</span></dd></div><div><dt>Excluded</dt><dd>{modelHealth.excludedCount}<span>quality-gated names</span></dd></div><div><dt>Top 20 churn</dt><dd>{formatRatio(modelHealth.top20ChurnRatio)}<span>{modelHealth.previousScoreDate ? `vs ${formatResearchDate(modelHealth.previousScoreDate)}` : "needs a prior run"}</span></dd></div><div><dt>Rank movement</dt><dd>{formatRatio(modelHealth.meanNormalizedRankChange)}<span>mean normalized change</span></dd></div></dl><div className="model-health-integrity"><span>Artifact hash <strong>{modelHealth.artifactHashMatches ? "Verified" : "Mismatch"}</strong></span><span>Registry hash <strong>{modelHealth.registryHashMatches ? "Verified" : "Mismatch"}</strong></span><span>Explanation lineage <strong>{modelHealth.explanationLineageMatches ? "Verified" : "Mismatch"}</strong></span><span>Forward readiness <strong>{modelHealth.forwardReadinessRecorded ? "Recorded" : "Missing"}</strong></span></div>{modelHealth.alerts.length ? <div className="model-health-alerts"><p>Warnings requiring review</p><ul>{modelHealth.alerts.map((alert) => <li key={`${alert.code}-${alert.metricKey}`}><div><strong>{readableMetric(alert.metricKey)}</strong><span>{alert.severity}</span></div><p>{alert.detail}</p></li>)}</ul></div> : <p className="model-health-clear">No threshold or integrity warning was recorded.</p>}<details className="model-input-disclosure"><summary>View active-feature health</summary><ul>{modelHealth.features.map((feature) => <li key={`${feature.featureKey}-${feature.featureVersion}`}><div><strong>{feature.displayName}</strong><span>{feature.availableCount} available · {feature.unavailableCount} unavailable</span></div><span>{formatRatio(feature.missingRatio)} missing · {feature.populationStabilityIndex ? `PSI ${Number(feature.populationStabilityIndex).toFixed(3)}` : "drift baseline forming"}</span></li>)}</ul></details><p className="model-health-hash">Snapshot {modelHealth.logicalSha256.slice(0, 12)}… · {modelHealth.modelVersion}</p></div> : <p className="quiet-copy">Health monitoring appears after a completed score publication and post-publication maintenance.</p>}</section>
    <section className="content-section methodology"><div><p className="eyebrow">METHOD</p><h2>How a score is formed</h2></div><div><p>{card?.methodology ?? "Sector-aware feature percentiles are averaged only when every required input is available."}</p><Link href="/rankings" className="text-link">Open dated rankings</Link></div></section>
    <section className="content-section methodology"><div><p className="eyebrow">FORECAST CONTEXT</p><h2>{predictionContext?.calibrationStatus === "supported" ? "Development-calibrated, still uncertain." : "Raw model output, not an expected return."}</h2></div><div>{predictionContext ? <><p>{predictionContext.calibrationStatus === "supported" ? "Basket percentages use a calibration fitted only on purged development validation folds." : "Purged development validation did not support converting the raw model percentage into a calibrated expected return. Quantrade shows it only as raw model output."}</p><dl><div><dt>Development error range</dt><dd>{formatPercentagePoints(predictionContext.residualLowerQuantile)} to {formatPercentagePoints(predictionContext.residualUpperQuantile)}</dd></div><div><dt>Monthly formations</dt><dd>{predictionContext.monthlyFormationCount}</dd></div><div><dt>Validation period</dt><dd>{formatResearchDate(predictionContext.developmentValidationStart)} to {formatResearchDate(predictionContext.developmentValidationEnd)}</dd></div><div><dt>Holdout used for fitting</dt><dd>No</dd></div></dl><p className="research-freshness-note">The range describes past development errors. It is not a confidence interval or a guarantee for the next portfolio.</p></> : <p>No development-only forecast context is registered for the active model.</p>}</div></section>
    <section className="content-section coverage-health"><div><p className="eyebrow">DATA COVERAGE</p><h2>What this run could score.</h2><p>Incomplete source data is withheld, never estimated or filled in.</p></div><div>{coverage.length ? <><p className="coverage-date">Latest completed run, {formatResearchDate(latestScores!.scoreDate)}</p><dl className="coverage-metrics"><div><dt>Eligible</dt><dd>{eligibleCount}<span>published scores</span></dd></div><div><dt>Withheld</dt><dd>{withheldCount}<span>quality-gated names</span></dd></div><div><dt>Coverage</dt><dd>{coveragePercent}%<span>of this run</span></dd></div></dl>{withheldCount ? <div className="coverage-gates"><p>Most common gates</p><ul>{gateBreakdown.map(([gate, count]) => <li key={gate}><span>{gate}</span><strong>{count} {count === 1 ? "name" : "names"}</strong></li>)}</ul></div> : <p className="coverage-complete">Every company in this run met the required data-quality gates.</p>}</> : <p className="quiet-copy">Coverage will appear after the first completed daily research run.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">RESEARCH ACTIVITY</p><h2>Recent score publications</h2></div><div>{recentRuns.length ? <ul className="publication-list">{recentRuns.map((run) => <li key={run.scoreDate}><strong>{formatResearchDate(run.scoreDate)}</strong><span>{run.eligibleCount} eligible names</span></li>)}</ul> : <p>No dated score publication has been recorded yet.</p>}</div></section>
    <section className="content-section operations-health"><div><p className="eyebrow">OPERATIONS</p><h2>Daily research health</h2><p>The local post-close workflow records every attempt and keeps published evidence intact when a later step fails.</p></div><div className="operations-list"><div><span>Latest operation</span><strong>{operations.latestRun ? operationStateLabel(operations.latestRun.state) : "Waiting for first run"}</strong><small>{operations.latestRun ? `${formatResearchDate(operations.latestRun.scoreDate)} · ${formatPublicationTime(operations.latestRun.lastEventAt)}${operations.latestRun.eligibleCount === undefined ? "" : ` · ${operations.latestRun.eligibleCount} eligible`}` : "No operation has been recorded."}</small>{operations.latestRun?.safeFailureMessage && <small>{operations.latestRun.safeFailureMessage}</small>}</div><div><span>Publication freshness</span><strong>{publicationFreshnessLabel(operations.publicationFreshness)}</strong><small>{operations.latestPublishedScoreDate ? `Scores ${formatResearchDate(operations.latestPublishedScoreDate)}` : "No score publication"}{operations.latestMarketSession ? ` · Stocks ${formatResearchDate(operations.latestMarketSession)}` : ""}{operations.latestBenchmarkSession ? ` · SPY ${formatResearchDate(operations.latestBenchmarkSession)}` : ""}</small></div><div><span>SEC checked</span><strong>{operations.latestSecRefreshAt ? formatPublicationTime(operations.latestSecRefreshAt) : "Unavailable"}</strong><small>This is retrieval freshness, not a claim that a filing was published at that time.</small></div><div><span>Next scheduled attempt</span><strong>{nextScheduledUpdate()}</strong><small>Requires this PC, a signed-in Windows session, PostgreSQL, and internet access. Codex and the web app may be closed.</small></div></div></section>
    <section className="content-section operations-history"><div><p className="eyebrow">RUN HISTORY</p><h2>Recent daily updates</h2><p>Retries and blocked duplicate attempts remain visible without creating another publication.</p></div><div>{operationsHistory.length ? <ol className="operations-history-list">{operationsHistory.map((run) => <li key={run.scoreDate}><div><strong>{formatResearchDate(run.scoreDate)}</strong><span>{runHistoryNote(run)}</span>{run.safeFailureMessage && <span>{run.safeFailureMessage}</span>}</div><div><strong>{operationStateLabel(run.state)}</strong><span>{run.eligibleCount === undefined ? formatPublicationTime(run.lastEventAt) : `${run.eligibleCount} eligible · ${formatPublicationTime(run.lastEventAt)}`}</span></div></li>)}</ol> : <p className="quiet-copy">Run history will appear after the first daily update.</p>}</div></section>
    <section className="content-section methodology" id="track-record"><div><p className="eyebrow">TRACK RECORD</p><h2>Monthly paper portfolio</h2></div><div>{portfolio ? <><p>An official monthly research basket, formed from scores dated {formatResearchDate(portfolio.scoreDate)} and recorded at the following regular-session open on {formatResearchDate(portfolio.executionDate)}. Daily score changes do not rebalance it.</p><dl><div><dt>Starting NAV</dt><dd>${Number(portfolio.startingNav).toLocaleString("en-CA")}</dd></div><div><dt>Positions</dt><dd>{portfolio.positions.length}</dd></div></dl><div className="portfolio-checkpoints"><p className="portfolio-checkpoints-title">Forward checkpoints</p><ul>{[5, 20, 60].map((horizon) => {
      const outcome = portfolio.outcomes.find((item) => item.horizonSessions === horizon);
      if (!outcome) return <li key={horizon}><strong>{horizon} sessions</strong><span>Awaiting its dated market close</span></li>;
      if (outcome.status === "withheld") return <li key={horizon}><strong>{horizon} sessions</strong><span>Withheld · {outcome.unavailableReason}</span></li>;
      const relative = Number(outcome.benchmarkRelativeReturn);
      return <li key={horizon}><strong>{horizon} sessions</strong><span className={relative >= 0 ? "positive-change" : "negative-change"}>{formatReturn(outcome.portfolioReturn!)} portfolio · {formatReturn(outcome.benchmarkRelativeReturn!)} vs SPY</span><small>{formatResearchDate(outcome.outcomeDate)}</small></li>;
    })}</ul><p className="portfolio-checkpoints-note">Each checkpoint uses the original next-open execution and its actual later market close. Missing marks or corporate actions are withheld, not estimated.</p></div></> : <p>No official monthly portfolio is active yet. The first one will be fixed from the final eligible score publication of a completed calendar month and recorded at the next regular-session open.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">ML FOUNDATION</p><h2>Future labels, tracked honestly.</h2></div><div>{forwardReadiness.length ? <><p>Each eligible score receives a future split-adjusted price-return label only after the relevant market window has closed. The minimum gate is {ML_DATASET_MINIMUM_COMPLETED_LABELS.toLocaleString("en-CA")} valid labels across {ML_DATASET_MINIMUM_SCORE_DATES} distinct research dates for every horizon.</p><dl className="ml-readiness-list">{forwardReadiness.map((item) => <div key={item.horizonSessions}><dt>{item.horizonSessions}-session label</dt><dd>{item.completedLabels.toLocaleString("en-CA")}<span>completed labels · {item.completedScoreDates}/{ML_DATASET_MINIMUM_SCORE_DATES} research dates</span><small>{item.withheldLabels.toLocaleString("en-CA")} withheld · {item.pendingLabels.toLocaleString("en-CA")} awaiting</small>{item.latestOutcomeDate && <time dateTime={item.latestOutcomeDate}>Latest: {formatResearchDate(item.latestOutcomeDate)}</time>}</dd></div>)}</dl><p className="ml-readiness-note">{datasetReady ? "Dataset minimum met. Model work may begin only with the existing walk-forward and holdout controls." : "Collection is in progress. No ML model will be trained or presented until every horizon meets this minimum."}</p></> : <p className="quiet-copy">Forward-label readiness will appear after the research database is connected.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">LIMITS</p><h2>Read uncertainty plainly.</h2></div><div><ul className="plain-list">{card?.limitations?.map((limitation) => <li key={limitation}>{limitation}</li>) ?? <><li>Tier B data does not verify historical constituent or delisting coverage.</li><li>A research score is not investment advice, a prediction, or a guarantee.</li><li>Unavailable data blocks publication instead of being substituted.</li></>}</ul>{unavailable && <p className="inline-notice">The stored model card is unavailable until the research database is connected.</p>}</div></section>
  </AppShell>;
}
