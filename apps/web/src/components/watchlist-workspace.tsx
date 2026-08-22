"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { formatScore } from "@/lib/format";
import type { DatedScore } from "@/lib/research-read-model";
import { readWatchlist, writeWatchlist, type WatchlistEntry } from "@/components/watchlist-storage";

export function WatchlistWorkspace({ scores, scoreDate }: { scores: DatedScore[]; scoreDate?: string }) {
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [removed, setRemoved] = useState<WatchlistEntry | null>(null);
  const scoresBySecurity = useMemo(() => new Map(scores.map((score) => [score.securityId, score])), [scores]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setWatchlist(readWatchlist());
      setHydrated(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const remove = (company: WatchlistEntry) => {
    const next = watchlist.filter((entry) => entry.securityId !== company.securityId);
    setWatchlist(next);
    writeWatchlist(next);
    setRemoved(company);
  };
  const undo = () => {
    if (!removed) return;
    const next = [...watchlist, removed];
    setWatchlist(next);
    writeWatchlist(next);
    setRemoved(null);
  };

  if (!hydrated) return <section className="empty-state small"><p className="eyebrow">WATCHLIST</p><h2>Loading your saved companies.</h2></section>;

  return <>
    {watchlist.length ? <ul className="grouped-list watchlist-list" aria-label="Saved companies">
      {watchlist.map((company) => {
        const score = scoresBySecurity.get(company.securityId);
        const href = `/stocks/${company.securityId}${scoreDate ? `?date=${scoreDate}&from=watchlist` : "?from=watchlist"}`;
        return <li key={company.securityId} className="watchlist-row">
          <Link className="watchlist-company" href={href}><strong>{company.ticker}</strong><span>{company.issuerName}</span></Link>
          {score?.eligible ? <div className="watchlist-score"><strong>{formatScore(score.score)}</strong><span>Rank {score.rank}</span></div> : <span className="watchlist-unavailable">{score ? "Score unavailable" : "No score published"}</span>}
          <details className="row-menu">
            <summary aria-label={`More actions for ${company.ticker}`}>•••</summary>
            <div className="row-menu-popover"><button type="button" onClick={() => remove(company)}>Remove from watchlist</button></div>
          </details>
        </li>;
      })}
    </ul> : <section className="empty-state small watchlist-empty-state"><p className="eyebrow">YOUR LIST</p><h2>Save companies worth returning to.</h2><p>Use the search field above to find a company, then save it from its research page.</p></section>}
    {removed && <aside className="undo-toast" role="status"><span>{removed.ticker} removed from watchlist.</span><button type="button" onClick={undo}>Undo</button></aside>}
  </>;
}
