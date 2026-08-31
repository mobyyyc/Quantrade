import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { getLatestPaperPortfolio, ResearchReadModelError } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";

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
            <p>This is a recorded monthly research object. Daily score and rank changes do not rewrite its membership.</p>
            <Link href="/research#track-record" className="text-link">Review the research method</Link>
          </div>
          <dl className="portfolio-home-facts">
            <div><dt>State</dt><dd>Active</dd><span>Official monthly record</span></div>
            <div><dt>Companies</dt><dd>{portfolio.positions.length}</dd><span>Held until the next formation</span></div>
            <div><dt>Model</dt><dd className="portfolio-model-name">{portfolio.modelVersion}</dd><span>Frozen deployed version</span></div>
          </dl>
        </section>
      ) : (
        <section className="empty-state small">
          <h2>Awaiting the first official basket.</h2>
          <p>The portfolio will appear after a completed calendar month is formed from its final eligible ranking and recorded at the next regular-session open.</p>
          <Link href="/research#track-record" className="primary-link">Read the methodology</Link>
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
