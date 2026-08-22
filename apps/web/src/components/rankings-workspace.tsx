"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { formatScore } from "@/lib/format";
import type { DatedScore, SecuritySearchResult } from "@/lib/research-read-model";

type WatchlistEntry = SecuritySearchResult;

const storageKey = "quantrade.watchlist.v1";

function readWatchlist(): WatchlistEntry[] {
  try {
    const stored = JSON.parse(window.localStorage.getItem(storageKey) ?? "[]") as unknown;
    if (!Array.isArray(stored)) return [];
    return stored.filter((item): item is WatchlistEntry => Boolean(
      item && typeof item === "object" && "securityId" in item && "ticker" in item && "issuerName" in item,
    ));
  } catch {
    return [];
  }
}

export function RankingsWorkspace({ scores, scoreDate }: { scores: DatedScore[]; scoreDate: string }) {
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SecuritySearchResult[]>([]);
  const [searchError, setSearchError] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setWatchlist(readWatchlist());
      setHydrated(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    if (hydrated) window.localStorage.setItem(storageKey, JSON.stringify(watchlist));
  }, [hydrated, watchlist]);
  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      const timer = window.setTimeout(() => { setResults([]); setSearchError(false); }, 0);
      return () => window.clearTimeout(timer);
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/v1/securities?query=${encodeURIComponent(term)}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Search failed");
        const body = await response.json() as { results: SecuritySearchResult[] };
        setResults(body.results);
        setSearchError(false);
      } catch (error) {
        if ((error as Error).name !== "AbortError") setSearchError(true);
      }
    }, 200);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [query]);

  const scoresBySecurity = useMemo(() => new Map(scores.map((score) => [score.securityId, score])), [scores]);
  const eligibleScores = scores.filter((score) => score.eligible);
  const add = (company: WatchlistEntry) => {
    setWatchlist((current) => current.some((item) => item.securityId === company.securityId) ? current : [...current, company]);
    setQuery("");
    setResults([]);
  };
  const remove = (securityId: string) => setWatchlist((current) => current.filter((item) => item.securityId !== securityId));

  return <>
    <section className="watchlist-section" aria-labelledby="watchlist-title">
      <div className="section-heading">
        <div><p className="eyebrow">PERSONAL LIST</p><h2 id="watchlist-title">My watchlist</h2></div>
        <span className="status-label">Saved on this device</span>
      </div>
      <div className="watchlist-add">
        <label htmlFor="watchlist-search">Add a company</label>
        <input id="watchlist-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search AAPL or Apple" autoComplete="off" />
      </div>
      {query.trim().length >= 2 && results.length > 0 && <ul className="watchlist-search-results" aria-label="Company search results">{results.map((company) => <li key={company.securityId}><div><strong>{company.ticker}</strong><span>{company.issuerName}</span></div><button type="button" onClick={() => add(company)} disabled={watchlist.some((item) => item.securityId === company.securityId)}>{watchlist.some((item) => item.securityId === company.securityId) ? "Added" : "Add"}</button></li>)}</ul>}
      {query.trim().length >= 2 && searchError && <p className="inline-notice">Company search is unavailable right now. Try again shortly.</p>}
      {watchlist.length ? <ul className="watchlist-list">{watchlist.map((company) => {
        const score = scoresBySecurity.get(company.securityId);
        return <li key={company.securityId} className="watchlist-row"><div className="watchlist-company"><Link href={`/stocks/${company.securityId}${score ? `?date=${scoreDate}` : ""}`}><strong>{company.ticker}</strong><span>{company.issuerName}</span></Link></div>{score?.eligible ? <div className="watchlist-score"><strong>{formatScore(score.score)}</strong><span>Rank {score.rank}</span></div> : <span className="watchlist-unavailable">No published score for this date</span>}<button type="button" className="quiet-button" onClick={() => remove(company.securityId)} aria-label={`Remove ${company.ticker} from watchlist`}>Remove</button></li>;
      })}</ul> : <p className="watchlist-empty">Add companies you want to revisit. Their latest published research score will appear here when available.</p>}
    </section>
    <section className="content-section ranking-section" aria-labelledby="rankings-list-title">
      <div className="section-heading"><div><p className="eyebrow">LATEST ELIGIBLE NAMES</p><h2 id="rankings-list-title">Ranked research candidates</h2></div><span className="status-label">{eligibleScores.length} eligible</span></div>
      {eligibleScores.length ? <ol className="score-list">{eligibleScores.map((score) => {
        const saved = watchlist.some((item) => item.securityId === score.securityId);
        return <li key={score.scoreSnapshotId} className="score-row score-row-action"><span className="rank-number">{score.rank ?? "—"}</span><div className="score-row-main"><Link href={`/stocks/${score.securityId}?date=${score.scoreDate}`} className="score-row-link"><strong>{score.ticker}</strong><span>{score.issuerName}</span></Link><span className="row-meta">{score.signal} research score</span></div><div className="score-row-value"><strong>{formatScore(score.score)}</strong><span>of 100</span></div><button type="button" className="quiet-button" onClick={() => saved ? remove(score.securityId) : add({ securityId: score.securityId, ticker: score.ticker, issuerName: score.issuerName })}>{saved ? "Remove" : "Add"}</button></li>;
      })}</ol> : <p className="empty-inline">No eligible research scores were published for this date.</p>}
    </section>
  </>;
}
