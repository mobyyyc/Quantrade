import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { ResearchReadModelError, searchSecurities, type SecuritySearchResult } from "@/lib/research-read-model";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ query?: string }> }) {
  const { query = "" } = await searchParams;
  let results: SecuritySearchResult[] = [];
  let unavailable = false;
  if (query.trim()) {
    try { results = await searchSecurities(query); } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  }
  return <AppShell current="/search">
    <section className="page-intro compact"><p className="eyebrow">SEARCH</p><h1>Find a company to research.</h1><p className="lede">Search by ticker or company name. No filters required.</p></section>
    <form className="search-form" action="/search"><label htmlFor="query">Ticker or company</label><div><input id="query" name="query" defaultValue={query} placeholder="For example, AAPL or Apple" /><button type="submit">Search</button></div></form>
    {query.trim() && <section className="content-section"><div className="section-heading"><div><p className="eyebrow">RESULTS</p><h2>{unavailable ? "Search is unavailable" : `${results.length} matching companies`}</h2></div></div>{unavailable ? <p className="empty-inline">Connect research data to search the current security master.</p> : <ul className="search-results">{results.map((result) => <li key={result.securityId}><Link href={`/stocks/${result.securityId}`}><strong>{result.ticker}</strong><span>{result.issuerName}</span></Link></li>)}</ul>}{!unavailable && !results.length && <p className="empty-inline">No matching company was found in the current security master.</p>}</section>}
  </AppShell>;
}
