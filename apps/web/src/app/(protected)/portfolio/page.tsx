import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { formatIssuerName, formatPercentagePoints, formatRelativeReturn, formatResearchDate, formatScore } from "@/lib/format";
import { getLatestPaperPortfolio, getPaperPortfolioHistory, PAPER_PORTFOLIO_ONE_WAY_COST_BPS, ResearchReadModelError, type PaperPortfolioHistoryEntry } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";

function formatWeight(value: string) {
  return `${(Number(value) * 100).toFixed(2).replace(/\.00$/, "")}%`;
}

function returnTone(value: string) {
  return Number(value) >= 0 ? "positive" : "negative";
}

function nextRebalanceRule(executionDate: string) {
  const date = new Date(`${executionDate}T00:00:00Z`);
  const month = new Intl.DateTimeFormat("en-CA", {
    month: "long", year: "numeric", timeZone: "UTC",
  }).format(date);
  return `First open after the final ${month} session`;
}

function gapReason(entry: PaperPortfolioHistoryEntry) {
  if (entry.status === "pending") return "20-session close not reached";
  if (entry.unavailableReason === "month_end_score_unavailable") return "Month-end score unavailable";
  if (entry.unavailableReason === "execution_window_missed") return "Next-open window missed";
  return entry.unavailableReason ?? "Did not pass the recorded data-quality checks";
}

export default async function PortfolioPage() {
  let portfolio: Awaited<ReturnType<typeof getLatestPaperPortfolio>> = null;
  let history: Awaited<ReturnType<typeof getPaperPortfolioHistory>> = [];
  let unavailable = false;
  try {
    [portfolio, history] = await Promise.all([
      getLatestPaperPortfolio(),
      getPaperPortfolioHistory(),
    ]);
  } catch (error) {
    if (!(error instanceof ResearchReadModelError)) throw error;
    unavailable = true;
  }

  return (
    <AppShell current="/portfolio">
      <section className="page-intro portfolio-intro">
        <p className="eyebrow">MODEL PORTFOLIO</p>
        <h1>A monthly basket, held to one rule.</h1>
        <p className="lede">Follow the official research portfolio separately from rankings that change each day.</p>
      </section>

      {unavailable ? (
        <section className="empty-state small">
          <h2>Portfolio data is not connected.</h2>
          <p>Connect the normalized research database to inspect the official monthly portfolio.</p>
        </section>
      ) : portfolio ? (
        <section className="portfolio-home-status" aria-labelledby="portfolio-status-title">
          <div className="portfolio-home-copy">
            <p className="eyebrow">CURRENT STATUS</p>
            <h2 id="portfolio-status-title">Official basket active.</h2>
            <p>The selection was fixed from the final monthly ranking before the next session. Its fill prices were recorded from that session&apos;s regular open after the market data passed validation. Daily score and rank changes do not rewrite it.</p>
            <Link href="/research#track-record" className="text-link">Review the research method</Link>
          </div>
          <dl className="portfolio-home-facts">
            <div><dt>Formation</dt><dd>{formatResearchDate(portfolio.scoreDate)}<span>Final eligible monthly ranking</span></dd></div>
            <div><dt>Next-open execution</dt><dd>{formatResearchDate(portfolio.executionDate)}<span>Recorded regular-session open</span></dd></div>
            <div><dt>Holdings</dt><dd>{portfolio.positions.length}<span>Fixed monthly positions</span></dd></div>
            <div><dt>Next rebalance</dt><dd className="portfolio-schedule">{nextRebalanceRule(portfolio.executionDate)}<span>Subject to a completed eligible score run</span></dd></div>
          </dl>
        </section>
      ) : (
        <section className="empty-state small">
          <h2>Awaiting the first official basket.</h2>
          <p>The portfolio will appear after a completed calendar month fixes its final eligible ranking and the next session&apos;s regular-open data passes validation.</p>
          <Link href="/research#track-record" className="primary-link">Read the methodology</Link>
        </section>
      )}

      {portfolio && (
        <section className="content-section portfolio-holdings" aria-labelledby="portfolio-holdings-title">
          <div className="portfolio-holdings-heading">
            <div>
              <p className="eyebrow">CURRENT HOLDINGS</p>
              <h2 id="portfolio-holdings-title">Recorded formation weights</h2>
            </div>
            <p>{portfolio.positions.length} positions · {portfolio.modelVersion}</p>
          </div>
          <div className="portfolio-holdings-columns" aria-hidden="true">
            <span>Rank</span><span>Company</span><span>Score</span><span>Weight</span>
          </div>
          <ol className="portfolio-holdings-list">
            {portfolio.positions.map((position) => (
              <li key={position.securityId}>
                <Link
                  href={`/stocks/${position.securityId}?date=${portfolio.scoreDate}&from=portfolio`}
                  aria-label={`${position.ticker}, formation rank ${position.rank}, score ${formatScore(position.score)} out of 100, ${formatWeight(position.weight)} formation weight`}
                >
                  <span className="portfolio-holding-rank">{position.rank}</span>
                  <span className="portfolio-holding-company"><strong>{position.ticker}</strong><span>{formatIssuerName(position.issuerName)}</span></span>
                  <span className="portfolio-holding-value"><strong>{formatScore(position.score)}</strong><small>/100</small></span>
                  <span className="portfolio-holding-value"><strong>{formatWeight(position.weight)}</strong><small>at formation</small></span>
                </Link>
              </li>
            ))}
          </ol>
          <p className="portfolio-holdings-note">Weights reflect the immutable next-open formation ledger. They are not recalculated from today&apos;s prices.</p>
        </section>
      )}

      <section className="content-section portfolio-history" aria-labelledby="portfolio-history-title">
        <div className="portfolio-history-heading">
          <div>
            <p className="eyebrow">FORMATION HISTORY</p>
            <h2 id="portfolio-history-title">Monthly formation record</h2>
          </div>
          <div className="portfolio-cost-note">
            <span>Cost assumption</span>
            <strong>{PAPER_PORTFOLIO_ONE_WAY_COST_BPS} bps × one-way turnover</strong>
            <small>Basket and SPY returns are gross. Estimated net difference subtracts this trading-cost case; commissions and taxes are not modeled.</small>
          </div>
        </div>

        {unavailable ? (
          <p className="portfolio-history-empty">History is unavailable while the research database is disconnected.</p>
        ) : history.length ? (
          <>
            <div className="portfolio-history-columns" aria-hidden="true">
              <span>Formation</span><span>Gross basket</span><span>Gross SPY</span><span>Est. net vs SPY</span><span>Turnover</span>
            </div>
            <ol className="portfolio-history-list">
              {history.map((entry) => {
                const completed = entry.status === "completed"
                  && entry.portfolioReturn !== undefined
                  && entry.benchmarkReturn !== undefined
                  && entry.estimatedNetBenchmarkRelativeReturn !== undefined;
                const stateLabel = entry.status === "pending" ? "Measurement pending"
                  : entry.status === "withheld" ? "Result withheld"
                  : entry.status === "missed" ? "Basket not formed"
                  : "Completed";
                return <li
                  key={`${entry.scoreDate}-${entry.modelVersion ?? entry.status}`}
                  aria-label={completed
                    ? `${formatResearchDate(entry.scoreDate)} formation, executed ${formatResearchDate(entry.executionDate)}, gross basket return ${formatRelativeReturn(entry.portfolioReturn!)}, gross ${entry.benchmarkTicker} return ${formatRelativeReturn(entry.benchmarkReturn!)}, estimated net difference ${formatPercentagePoints(entry.estimatedNetBenchmarkRelativeReturn!)}, one-way turnover ${formatWeight(entry.oneWayTurnover)}`
                    : `${formatResearchDate(entry.scoreDate)} formation, ${stateLabel}. ${gapReason(entry)}`}
                >
                  <span className="portfolio-history-formation">
                    <strong>{formatResearchDate(entry.scoreDate)}</strong>
                    <small>{completed ? `${entry.positionCount} names · closed ${formatResearchDate(entry.outcomeDate!)}` : `${gapReason(entry)} · expected open ${formatResearchDate(entry.executionDate)}`}</small>
                  </span>
                  {completed ? <>
                    <span className={returnTone(entry.portfolioReturn!)}>{formatRelativeReturn(entry.portfolioReturn!)}</span>
                    <span className={returnTone(entry.benchmarkReturn!)}>{formatRelativeReturn(entry.benchmarkReturn!)}</span>
                    <span className={returnTone(entry.estimatedNetBenchmarkRelativeReturn!)}>{formatPercentagePoints(entry.estimatedNetBenchmarkRelativeReturn!)}</span>
                    <span className="portfolio-history-turnover">{formatWeight(entry.oneWayTurnover)}</span>
                  </> : <>
                    <span className="portfolio-history-state">{stateLabel}</span>
                    <span aria-hidden="true">—</span><span aria-hidden="true">—</span><span aria-hidden="true">—</span>
                  </>}
                </li>;
              })}
            </ol>
            <p className="portfolio-history-note">Turnover compares immutable target weights with the preceding official basket; the first basket measures deployment from cash. Missing formations remain visible and are never reconstructed later.</p>
          </>
        ) : (
          <p className="portfolio-history-empty">No official monthly formation has been recorded yet.</p>
        )}
      </section>

      <section className="content-section portfolio-contract">
        <div>
          <p className="eyebrow">PORTFOLIO CONTRACT</p>
          <h2>What this page follows</h2>
        </div>
        <dl>
          <div><dt>Monthly, not daily</dt><dd>The final eligible ranking of a completed month determines the next basket.</dd></div>
          <div><dt>Recorded, not reconstructed</dt><dd>Each selection and next-open fill ledger is stored as a dated object. Later rankings cannot alter its holdings, and a missed formation is not backfilled.</dd></div>
          <div><dt>Research, not instruction</dt><dd>The basket is a model-tracking tool, not personalized investment advice or a return guarantee.</dd></div>
        </dl>
      </section>
    </AppShell>
  );
}
