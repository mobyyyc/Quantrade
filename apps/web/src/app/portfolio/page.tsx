import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { formatIssuerName, formatResearchDate, formatScore } from "@/lib/format";
import { getLatestPaperPortfolio, ResearchReadModelError } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";

function formatWeight(value: string) {
  return `${(Number(value) * 100).toFixed(2).replace(/\.00$/, "")}%`;
}

function nextRebalanceRule(executionDate: string) {
  const date = new Date(`${executionDate}T00:00:00Z`);
  const month = new Intl.DateTimeFormat("en-CA", {
    month: "long", year: "numeric", timeZone: "UTC",
  }).format(date);
  return `First open after the final ${month} session`;
}

export default async function PortfolioPage() {
  let portfolio: Awaited<ReturnType<typeof getLatestPaperPortfolio>> = null;
  let unavailable = false;
  try {
    portfolio = await getLatestPaperPortfolio();
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
            <p>These holdings were recorded at the next regular-session open. Daily score and rank changes do not rewrite them.</p>
            <Link href="/research#track-record" className="text-link">Review the research method</Link>
          </div>
          <dl className="portfolio-home-facts">
            <div><dt>Formation</dt><dd>{formatResearchDate(portfolio.scoreDate)}</dd><span>Final eligible monthly ranking</span></div>
            <div><dt>Next-open execution</dt><dd>{formatResearchDate(portfolio.executionDate)}</dd><span>Recorded regular-session open</span></div>
            <div><dt>Holdings</dt><dd>{portfolio.positions.length}</dd><span>Fixed monthly positions</span></div>
            <div><dt>Next rebalance</dt><dd className="portfolio-schedule">{nextRebalanceRule(portfolio.executionDate)}</dd><span>Subject to a completed eligible score run</span></div>
          </dl>
        </section>
      ) : (
        <section className="empty-state small">
          <h2>Awaiting the first official basket.</h2>
          <p>The portfolio will appear after a completed calendar month is formed from its final eligible ranking and recorded at the next regular-session open.</p>
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

      <section className="content-section portfolio-contract">
        <div>
          <p className="eyebrow">PORTFOLIO CONTRACT</p>
          <h2>What this page follows</h2>
        </div>
        <dl>
          <div><dt>Monthly, not daily</dt><dd>The final eligible ranking of a completed month determines the next basket.</dd></div>
          <div><dt>Recorded, not reconstructed</dt><dd>Each portfolio is stored as a dated object so later rankings cannot alter its history.</dd></div>
          <div><dt>Research, not instruction</dt><dd>The basket is a model-tracking tool, not personalized investment advice or a return guarantee.</dd></div>
        </dl>
      </section>
    </AppShell>
  );
}
