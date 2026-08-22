"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { formatScore } from "@/lib/format";
import type { DatedScore } from "@/lib/research-read-model";
import { readWatchlist, type WatchlistEntry } from "@/components/watchlist-storage";

export function WatchlistPreview({ scores, scoreDate }: { scores: DatedScore[]; scoreDate?: string }) {
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const scoresBySecurity = useMemo(() => new Map(scores.map((score) => [score.securityId, score])), [scores]);
  useEffect(() => {
    const timer = window.setTimeout(() => setWatchlist(readWatchlist()), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return <section className="watchlist-preview" aria-labelledby="watchlist-preview-title">
    <div className="section-heading"><div><p className="eyebrow">YOUR LIST</p><h2 id="watchlist-preview-title">Watchlist</h2></div><Link className="text-link" href="/watchlist">View all</Link></div>
    {watchlist.length ? <ul className="compact-company-list">
      {watchlist.slice(0, 3).map((company) => {
        const score = scoresBySecurity.get(company.securityId);
        return <li key={company.securityId}><Link href={`/stocks/${company.securityId}${scoreDate ? `?date=${scoreDate}&from=watchlist` : "?from=watchlist"}`}><strong>{company.ticker}</strong><span>{score?.eligible ? `Score ${formatScore(score.score)} · Rank ${score.rank}` : "No published score"}</span></Link></li>;
      })}
    </ul> : <p className="watchlist-preview-empty">Save companies from search or a stock detail page to keep them in view here.</p>}
  </section>;
}
