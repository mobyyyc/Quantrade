"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { formatIssuerName, formatScore } from "@/lib/format";
import type { ScoreListItem } from "@/components/score-list";

const ROW_HEIGHT = 86;
const INITIAL_VIEWPORT_HEIGHT = 592;

export function TodayRankingStream({ scores }: { scores: ScoreListItem[] }) {
  const regionRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ top: false, bottom: scores.length * ROW_HEIGHT > INITIAL_VIEWPORT_HEIGHT });

  useEffect(() => {
    const region = regionRef.current;
    if (!region) return;
    const update = () => {
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

  return <div className={`scroll-fade-frame today-ranking-scroll${edges.top ? " has-top-fade" : ""}${edges.bottom ? " has-bottom-fade" : ""}`}><div ref={regionRef} className="scroll-fade-region" role="region" tabIndex={0} aria-label="Ranked research candidates. Scroll to see more."><ol className="score-list score-list-today">
    {scores.map((score) => {
      return <li key={score.scoreSnapshotId} className="score-row">
        <Link href={`/stocks/${score.securityId}?date=${score.scoreDate}&from=today`} className="score-row-link" aria-label={`Open research detail for ${score.ticker}, score ${formatScore(score.score)} out of 100`}>
          <span className="rank-number">{score.rank ?? "Unavailable"}</span>
          <div className="score-row-main"><strong>{score.ticker}</strong><span>{formatIssuerName(score.issuerName)}</span></div>
          <div className="score-row-value"><span className="score-unit"><strong>{formatScore(score.score)}</strong><span>/100</span></span></div>
        </Link>
      </li>;
    })}
  </ol></div></div>;
}
