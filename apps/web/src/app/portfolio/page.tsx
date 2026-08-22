import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { ResearchNotice } from "@/components/research-notice";
import { formatResearchDate } from "@/lib/format";
import { getLatestPaperPortfolio } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";

export default async function PortfolioPage() {
  let portfolio = null;
  try { portfolio = await getLatestPaperPortfolio(); } catch { portfolio = null; }
  return <AppShell current="/portfolio"><section className="page-intro compact"><p className="eyebrow">PAPER PORTFOLIO</p><h1>Track a dated research basket.</h1><p className="lede">This is a private research ledger. It records the next-session-open execution of eligible dated scores, not real trades.</p></section>{portfolio ? <section className="content-section"><div className="section-heading"><div><p className="eyebrow">SCORED {formatResearchDate(portfolio.scoreDate)} · EXECUTED {formatResearchDate(portfolio.executionDate)}</p><h2>${Number(portfolio.startingNav).toLocaleString("en-CA")} starting research NAV</h2></div><span className="status-label">{portfolio.positions.length} positions</span></div><ul className="watchlist-list">{portfolio.positions.map((position) => <li className="watchlist-row" key={position.securityId}><Link className="watchlist-company" href={`/stocks/${position.securityId}?date=${portfolio.scoreDate}`}><strong>{position.ticker}</strong><span>{position.issuerName}</span></Link><span className="watchlist-unavailable">{Number(position.quantity).toFixed(4)} shares</span></li>)}</ul></section> : <section className="empty-state small"><p className="eyebrow">WAITING FOR EXECUTION</p><h2>No paper portfolio is published yet.</h2><p>After a score run has 20 eligible names and the following regular-session open is available, publish the immutable paper portfolio from the research service.</p></section>}<ResearchNotice /></AppShell>;
}
