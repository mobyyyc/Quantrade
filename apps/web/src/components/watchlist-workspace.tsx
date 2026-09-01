"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { formatPriceChange, formatResearchDate, formatScore, formatUsdPrice } from "@/lib/format";
import type { DatedScore, LatestPriceSummary } from "@/lib/research-read-model";
import { maximumWatchlistTags, readWatchlist, writeWatchlist, type WatchlistEntry } from "@/components/watchlist-storage";

function formatScoreDelta(value: number) {
  const absolute = Math.abs(value).toFixed(1).replace(/\.0$/, "");
  return `${value > 0 ? "+" : "−"}${absolute} pts`;
}

function movementSincePrevious(score?: DatedScore, previous?: DatedScore) {
  if (!score || !previous) return null;
  if (score.eligible !== previous.eligible) return score.eligible ? "Newly eligible" : "No longer eligible";
  if (!score.eligible || score.rank === undefined || previous.rank === undefined) return null;
  const scoreDelta = Number(score.score) - Number(previous.score);
  const rankDelta = previous.rank - score.rank;
  const changes = [
    ...(rankDelta ? [`${rankDelta > 0 ? "↑" : "↓"} ${Math.abs(rankDelta)} ${Math.abs(rankDelta) === 1 ? "rank" : "ranks"}`] : []),
    ...(scoreDelta ? [formatScoreDelta(scoreDelta)] : []),
  ];
  return changes.length ? changes.join(" · ") : null;
}

function normalizedDraftTags(value: string) {
  const seen = new Set<string>();
  return value.split(",").map((tag) => tag.trim().replace(/\s+/g, " ")).filter((tag) => {
    const key = tag.toLocaleLowerCase();
    if (!tag || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function WatchlistWorkspace({
  scores,
  scoreDate,
  previousScores,
  previousScoreDate,
}: {
  scores: DatedScore[];
  scoreDate?: string;
  previousScores: DatedScore[];
  previousScoreDate?: string;
}) {
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [removed, setRemoved] = useState<WatchlistEntry | null>(null);
  const [prices, setPrices] = useState<LatestPriceSummary[]>([]);
  const [pricesUnavailable, setPricesUnavailable] = useState(false);
  const [sortBy, setSortBy] = useState<"score" | "ticker">("score");
  const [editingSecurityId, setEditingSecurityId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [tagsDraft, setTagsDraft] = useState("");
  const [editorError, setEditorError] = useState<string | null>(null);
  const scrollRegionRef = useRef<HTMLDivElement>(null);
  const [scrollEdges, setScrollEdges] = useState({ top: false, bottom: false });
  const scoresBySecurity = useMemo(() => new Map(scores.map((score) => [score.securityId, score])), [scores]);
  const previousScoresBySecurity = useMemo(() => new Map(previousScores.map((score) => [score.securityId, score])), [previousScores]);
  const pricesBySecurity = useMemo(() => new Map(prices.map((price) => [price.securityId, price])), [prices]);
  const watchlistSecurityIds = useMemo(() => watchlist.map((entry) => entry.securityId).join(","), [watchlist]);
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
    if (!hydrated || !watchlistSecurityIds) return;
    const controller = new AbortController();
    const loadPrices = async () => {
      try {
        const response = await fetch(`/api/v1/prices?securityIds=${encodeURIComponent(watchlistSecurityIds)}`, { signal: controller.signal });
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
  }, [hydrated, watchlistSecurityIds]);

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
  }, [orderedWatchlist.length, editingSecurityId]);

  const remove = (company: WatchlistEntry) => {
    const next = watchlist.filter((entry) => entry.securityId !== company.securityId);
    setWatchlist(next);
    writeWatchlist(next);
    setRemoved(company);
    if (editingSecurityId === company.securityId) setEditingSecurityId(null);
  };
  const undo = () => {
    if (!removed) return;
    const next = [...watchlist, removed];
    setWatchlist(next);
    writeWatchlist(next);
    setRemoved(null);
  };
  const beginEditing = (company: WatchlistEntry) => {
    setEditingSecurityId(company.securityId);
    setNoteDraft(company.note ?? "");
    setTagsDraft(company.tags?.join(", ") ?? "");
    setEditorError(null);
  };
  const cancelEditing = () => {
    setEditingSecurityId(null);
    setEditorError(null);
  };
  const saveResearchContext = (event: FormEvent<HTMLFormElement>, company: WatchlistEntry) => {
    event.preventDefault();
    const tags = normalizedDraftTags(tagsDraft);
    if (tags.length > maximumWatchlistTags) {
      setEditorError(`Use no more than ${maximumWatchlistTags} tags.`);
      return;
    }
    if (tags.some((tag) => tag.length > 24)) {
      setEditorError("Keep each tag to 24 characters or fewer.");
      return;
    }
    const note = noteDraft.trim();
    const next = watchlist.map((entry) => entry.securityId === company.securityId ? {
      ...entry,
      ...(note ? { note } : { note: undefined }),
      ...(tags.length ? { tags } : { tags: undefined }),
    } : entry);
    setWatchlist(next);
    writeWatchlist(next);
    setEditingSecurityId(null);
    setEditorError(null);
  };

  if (!hydrated) return <section className="empty-state small"><p className="eyebrow">WATCHLIST</p><h2>Loading your saved companies.</h2></section>;

  return <>
    {watchlist.length ? <>
      <div className="watchlist-toolbar">
        <span>{watchlist.length} saved{previousScoreDate ? ` · Changes since ${formatResearchDate(previousScoreDate)}` : ""}</span>
        <div className="segmented-control" aria-label="Watchlist sort order"><button type="button" className={sortBy === "score" ? "segment-active" : ""} aria-pressed={sortBy === "score"} onClick={() => setSortBy("score")}>Score</button><button type="button" className={sortBy === "ticker" ? "segment-active" : ""} aria-pressed={sortBy === "ticker"} onClick={() => setSortBy("ticker")}>Ticker</button></div>
      </div>
      <div className={`watchlist-scroll-frame${scrollEdges.top ? " has-top-fade" : ""}${scrollEdges.bottom ? " has-bottom-fade" : ""}`}>
        <div ref={scrollRegionRef} className="watchlist-scroll-region" tabIndex={0} aria-label="Saved companies. Scroll to see more.">
          <ul className="grouped-list watchlist-list">
            {orderedWatchlist.map((company) => {
              const score = scoresBySecurity.get(company.securityId);
              const previousScore = previousScoresBySecurity.get(company.securityId);
              const movement = previousScoreDate ? movementSincePrevious(score, previousScore) : null;
              const movementTitle = previousScoreDate ? `Compared with ${formatResearchDate(previousScoreDate)}` : undefined;
              const price = pricesBySecurity.get(company.securityId);
              const change = price ? formatPriceChange(price.closePrice, price.previousClosePrice) : null;
              const href = `/stocks/${company.securityId}${scoreDate ? `?date=${scoreDate}&from=watchlist` : "?from=watchlist"}`;
              const isEditing = editingSecurityId === company.securityId;
              const hasResearchContext = Boolean(company.note || company.tags?.length);
              return <li key={company.securityId} className={`watchlist-row${isEditing ? " is-editing" : ""}`}>
                <div className="watchlist-row-main">
                  <Link className="watchlist-company" href={href}><strong>{company.ticker}</strong><span>{company.issuerName}</span></Link>
                  <div className="watchlist-market">
                    {price ? <><strong>{formatUsdPrice(price.closePrice)}</strong>{change ? <span className={change.direction === "positive" ? "positive-change" : "negative-change"}>{change.amount} ({change.percent})</span> : <span>Latest close</span>}</> : <span>{pricesUnavailable ? "Price unavailable" : "Loading price"}</span>}
                  </div>
                  {score?.eligible ? <div className="watchlist-score"><span className="score-unit"><strong>{formatScore(score.score)}</strong><span>/100</span></span><span>Rank {score.rank}</span>{movement ? <small className="watchlist-change" title={movementTitle}>{movement}</small> : null}</div> : <div className="watchlist-score watchlist-score-unavailable"><span className="watchlist-unavailable">{score ? "Score unavailable" : "No score published"}</span>{movement ? <small className="watchlist-change" title={movementTitle}>{movement}</small> : null}</div>}
                  <details className="row-menu">
                    <summary aria-label={`More actions for ${company.ticker}`}>•••</summary>
                    <div className="row-menu-popover">
                      <button type="button" onClick={(event) => { beginEditing(company); event.currentTarget.closest("details")?.removeAttribute("open"); }}>{hasResearchContext ? "Edit note and tags" : "Add note and tags"}</button>
                      <button type="button" onClick={() => remove(company)}>Remove from watchlist</button>
                    </div>
                  </details>
                </div>
                {!isEditing && hasResearchContext ? <div className="watchlist-personal-context">
                  {company.note ? <p>{company.note}</p> : null}
                  {company.tags?.length ? <ul aria-label={`Tags for ${company.ticker}`}>{company.tags.map((tag) => <li key={tag}>{tag}</li>)}</ul> : null}
                </div> : null}
                {isEditing ? <form className="watchlist-editor" onSubmit={(event) => saveResearchContext(event, company)}>
                  <div className="watchlist-editor-fields">
                    <label>Private note<textarea value={noteDraft} onChange={(event) => { setNoteDraft(event.target.value); setEditorError(null); }} maxLength={240} rows={3} placeholder="What makes this company worth revisiting?" autoFocus /></label>
                    <label>Tags<input value={tagsDraft} onChange={(event) => { setTagsDraft(event.target.value); setEditorError(null); }} maxLength={149} placeholder="Earnings, valuation, follow-up" /></label>
                  </div>
                  <div className="watchlist-editor-footer">
                    <p>{editorError ? <span role="alert">{editorError}</span> : `Stored only in this browser. Use up to ${maximumWatchlistTags} comma-separated tags.`}</p>
                    <div><button type="button" className="quiet-button" onClick={cancelEditing}>Cancel</button><button type="submit" className="primary-button">Save</button></div>
                  </div>
                </form> : null}
              </li>;
            })}
          </ul>
        </div>
      </div>
    </> : <section className="empty-state small watchlist-empty-state"><p className="eyebrow">YOUR LIST</p><h2>Save companies worth returning to.</h2><p>Use the search field above to find a company, then save it from its research page.</p></section>}
    {removed && <aside className="undo-toast" role="status"><span>{removed.ticker} removed from watchlist.</span><button type="button" onClick={undo}>Undo</button></aside>}
  </>;
}
