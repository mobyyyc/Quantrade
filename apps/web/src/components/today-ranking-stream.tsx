"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { formatIssuerName, formatScore } from "@/lib/format";
import type { DatedScore } from "@/lib/research-read-model";

const ROW_HEIGHT = 86;
const OVERSCAN = 5;
const INITIAL_VIEWPORT_HEIGHT = 592;

export function TodayRankingStream({ scores }: { scores: DatedScore[] }) {
  const regionRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(INITIAL_VIEWPORT_HEIGHT);
  const [edges, setEdges] = useState({ top: false, bottom: scores.length * ROW_HEIGHT > INITIAL_VIEWPORT_HEIGHT });
  const range = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
    const end = Math.min(scores.length, Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + OVERSCAN);
    return { start, end };
  }, [scores.length, scrollTop, viewportHeight]);

  useEffect(() => {
    const region = regionRef.current;
    if (!region) return;
    const update = () => {
      setViewportHeight(region.clientHeight);
      setScrollTop(region.scrollTop);
      setEdges({
        top: region.scrollTop > 2,
        bottom: region.scrollTop + region.clientHeight < region.scrollHeight - 2,
      });
    };
    update();
    region.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(region);
    return () => {
      region.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, []);

  return <div className={`scroll-fade-frame today-ranking-scroll${edges.top ? " has-top-fade" : ""}${edges.bottom ? " has-bottom-fade" : ""}`}><div ref={regionRef} className="scroll-fade-region" tabIndex={0} aria-label="Ranked research candidates. Scroll to see more."><ol className="score-list score-list-today today-virtual-list" style={{ height: `${scores.length * ROW_HEIGHT}px` }}>
    {scores.slice(range.start, range.end).map((score, offset) => {
      const index = range.start + offset;
      return <li key={score.scoreSnapshotId} className="score-row today-virtual-row" aria-posinset={index + 1} style={{ transform: `translateY(${index * ROW_HEIGHT}px)` }}>
        <Link href={`/stocks/${score.securityId}?date=${score.scoreDate}&from=today`} className="score-row-link" aria-label={`Open research detail for ${score.ticker}, score ${formatScore(score.score)} out of 100`}>
          <span className="rank-number">{score.rank ?? "Unavailable"}</span>
          <div className="score-row-main"><strong>{score.ticker}</strong><span>{formatIssuerName(score.issuerName)}</span></div>
          <div className="score-row-value"><span className="score-unit"><strong>{formatScore(score.score)}</strong><span>/100</span></span></div>
        </Link>
      </li>;
    })}
  </ol></div></div>;
}
