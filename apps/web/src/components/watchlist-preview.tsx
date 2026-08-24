"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { formatMarketSessionDate, formatPriceChange, formatScore, formatUsdPrice } from "@/lib/format";
import type { DatedScore, LatestPriceSummary } from "@/lib/research-read-model";
import { readWatchlist, type WatchlistEntry } from "@/components/watchlist-storage";

export function WatchlistPreview({ scores, scoreDate }: { scores: DatedScore[]; scoreDate?: string }) {
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [prices, setPrices] = useState<LatestPriceSummary[]>([]);
  const [pricesUnavailable, setPricesUnavailable] = useState(false);
  const scoresBySecurity = useMemo(() => new Map(scores.map((score) => [score.securityId, score])), [scores]);
  const pricesBySecurity = useMemo(() => new Map(prices.map((price) => [price.securityId, price])), [prices]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setWatchlist(readWatchlist());
      setHydrated(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    if (!hydrated || !watchlist.length) return;
    const controller = new AbortController();
    const loadPrices = async () => {
      try {
        const response = await fetch(`/api/v1/prices?securityIds=${encodeURIComponent(watchlist.map((entry) => entry.securityId).join(","))}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Price request failed");
        const body = await response.json() as { prices: LatestPriceSummary[] };
        setPrices(body.prices);
        setPricesUnavailable(false);
      } catch (error) {
        if ((error as Error).name !== "AbortError") setPricesUnavailable(true);
      }
    };
    void loadPrices();
    return () => controller.abort();
  }, [hydrated, watchlist]);

  return <section className="watchlist-preview" aria-labelledby="watchlist-preview-title">
    <div className="section-heading"><div><p className="eyebrow">YOUR LIST</p><h2 id="watchlist-preview-title">Watchlist</h2></div><Link className="text-link" href="/watchlist">View all</Link></div>
    {watchlist.length ? <ul className="compact-company-list">
      {watchlist.slice(0, 3).map((company) => {
        const score = scoresBySecurity.get(company.securityId);
        const price = pricesBySecurity.get(company.securityId);
        const change = price ? formatPriceChange(price.closePrice, price.previousClosePrice) : null;
        return <li key={company.securityId}><Link className="compact-company-link" href={`/stocks/${company.securityId}${scoreDate ? `?date=${scoreDate}&from=watchlist` : "?from=watchlist"}`}><span className="compact-company-identity"><strong>{company.ticker}</strong><span>{company.issuerName}</span></span><span className="compact-company-market">{price ? <><strong>{formatUsdPrice(price.closePrice)}</strong><span className={change?.direction === "positive" ? "positive-change" : change?.direction === "negative" ? "negative-change" : ""}>{change ? change.percent : `${formatMarketSessionDate(price.sessionDate)} close`}</span></> : <span>{pricesUnavailable ? "Price unavailable" : "Latest price"}</span>}</span>{score?.eligible ? <span className="compact-company-score"><span className="score-unit"><strong>{formatScore(score.score)}</strong><span>/100</span></span><small>Rank {score.rank} · {price ? formatMarketSessionDate(price.sessionDate) : "Latest close"}</small></span> : <span className="compact-company-score compact-company-unavailable"><small>{score ? "Score unavailable" : "No score published"}</small></span>}</Link></li>;
      })}
    </ul> : <p className="watchlist-preview-empty">Save companies from search or a stock detail page to keep them in view here.</p>}
  </section>;
}
