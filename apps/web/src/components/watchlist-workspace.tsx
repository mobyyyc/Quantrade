"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { formatPriceChange, formatScore, formatUsdPrice } from "@/lib/format";
import type { DatedScore, LatestPriceSummary } from "@/lib/research-read-model";
import { readWatchlist, writeWatchlist, type WatchlistEntry } from "@/components/watchlist-storage";

export function WatchlistWorkspace({ scores, scoreDate }: { scores: DatedScore[]; scoreDate?: string }) {
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [removed, setRemoved] = useState<WatchlistEntry | null>(null);
  const [prices, setPrices] = useState<LatestPriceSummary[]>([]);
  const [pricesUnavailable, setPricesUnavailable] = useState(false);
  const [sortBy, setSortBy] = useState<"score" | "ticker">("score");
  const scrollRegionRef = useRef<HTMLDivElement>(null);
  const [scrollEdges, setScrollEdges] = useState({ top: false, bottom: false });
  const scoresBySecurity = useMemo(() => new Map(scores.map((score) => [score.securityId, score])), [scores]);
  const pricesBySecurity = useMemo(() => new Map(prices.map((price) => [price.securityId, price])), [prices]);
  const orderedWatchlist = useMemo(() => [...watchlist].sort((left, right) => {
    if (sortBy === "ticker") return left.ticker.localeCompare(right.ticker);
    const leftScore = Number(scoresBySecurity.get(left.securityId)?.score ?? -1);
    const rightScore = Number(scoresBySecurity.get(right.securityId)?.score ?? -1);
    return rightScore - leftScore || left.ticker.localeCompare(right.ticker);
  }), [scoresBySecurity, sortBy, watchlist]);

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

  useEffect(() => {
    const region = scrollRegionRef.current;
    if (!region) return;
    const updateEdges = () => setScrollEdges({
      top: region.scrollTop > 2,
      bottom: region.scrollTop + region.clientHeight < region.scrollHeight - 2,
    });
    updateEdges();
    region.addEventListener("scroll", updateEdges, { passive: true });
    const observer = new ResizeObserver(updateEdges);
    observer.observe(region);
    return () => {
      region.removeEventListener("scroll", updateEdges);
      observer.disconnect();
    };
  }, [orderedWatchlist.length]);

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
    {watchlist.length ? <><div className="watchlist-toolbar"><span>{watchlist.length} saved</span><div className="segmented-control" aria-label="Watchlist sort order"><button type="button" className={sortBy === "score" ? "segment-active" : ""} aria-pressed={sortBy === "score"} onClick={() => setSortBy("score")}>Score</button><button type="button" className={sortBy === "ticker" ? "segment-active" : ""} aria-pressed={sortBy === "ticker"} onClick={() => setSortBy("ticker")}>Ticker</button></div></div><div className={`watchlist-scroll-frame${scrollEdges.top ? " has-top-fade" : ""}${scrollEdges.bottom ? " has-bottom-fade" : ""}`}><div ref={scrollRegionRef} className="watchlist-scroll-region" tabIndex={0} aria-label="Saved companies. Scroll to see more."><ul className="grouped-list watchlist-list">
      {orderedWatchlist.map((company) => {
        const score = scoresBySecurity.get(company.securityId);
        const price = pricesBySecurity.get(company.securityId);
        const change = price ? formatPriceChange(price.closePrice, price.previousClosePrice) : null;
        const href = `/stocks/${company.securityId}${scoreDate ? `?date=${scoreDate}&from=watchlist` : "?from=watchlist"}`;
        return <li key={company.securityId} className="watchlist-row">
          <Link className="watchlist-company" href={href}><strong>{company.ticker}</strong><span>{company.issuerName}</span></Link>
          <div className="watchlist-market">
            {price ? <><strong>{formatUsdPrice(price.closePrice)}</strong>{change ? <span className={change.direction === "positive" ? "positive-change" : "negative-change"}>{change.amount} ({change.percent})</span> : <span>Latest close</span>}</> : <span>{pricesUnavailable ? "Price unavailable" : "Loading price"}</span>}
          </div>
          {score?.eligible ? <div className="watchlist-score"><strong>{formatScore(score.score)}</strong><span>Rank {score.rank}</span></div> : <span className="watchlist-unavailable">{score ? "Score unavailable" : "No score published"}</span>}
          <details className="row-menu">
            <summary aria-label={`More actions for ${company.ticker}`}>•••</summary>
            <div className="row-menu-popover"><button type="button" onClick={() => remove(company)}>Remove from watchlist</button></div>
          </details>
        </li>;
      })}
    </ul></div></div></> : <section className="empty-state small watchlist-empty-state"><p className="eyebrow">YOUR LIST</p><h2>Save companies worth returning to.</h2><p>Use the search field above to find a company, then save it from its research page.</p></section>}
    {removed && <aside className="undo-toast" role="status"><span>{removed.ticker} removed from watchlist.</span><button type="button" onClick={undo}>Undo</button></aside>}
  </>;
}
