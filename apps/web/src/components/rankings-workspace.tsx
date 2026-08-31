"use client";

import { useState } from "react";
import Link from "next/link";
import { ScoreList } from "@/components/score-list";
import { ResearchBasket } from "@/components/research-basket";
import { formatIssuerName, formatPublicationTime, formatResearchDate, formatScore } from "@/lib/format";
import type { DatedScore, PaperPortfolio } from "@/lib/research-read-model";

const initialVisibleCount = 25;

export function RankingsWorkspace({ scores, scoreDate, previousScoreDate, previousScores, portfolio, previewBasket = false }: { scores: DatedScore[]; scoreDate: string; previousScoreDate?: string; previousScores: DatedScore[]; portfolio: PaperPortfolio | null; previewBasket?: boolean }) {
  const [visibleCount, setVisibleCount] = useState(initialVisibleCount);
  const eligibleScores = scores.filter((score) => score.eligible);
  const withheldCount = scores.length - eligibleScores.length;
  const publishedAt = scores.find((score) => score.publishedAt)?.publishedAt;
  const visibleScores = eligibleScores.slice(0, visibleCount);
  const priorScores = new Map(previousScores.filter((score) => score.eligible).map((score) => [score.securityId, score]));
  const movers = eligibleScores.flatMap((score) => {
    const prior = priorScores.get(score.securityId);
    if (!prior) return [];
    const change = Number(formatScore(score.score)) - Number(formatScore(prior.score));
    return change ? [{ score, change }] : [];
  }).sort((left, right) => Math.abs(right.change) - Math.abs(left.change)).slice(0, 3);

  return <section className="rankings-layout" aria-labelledby="rankings-list-title">
    <div className="rankings-context" aria-label="Ranking context">
      <p className="eyebrow">PUBLISHED COVERAGE</p>
      <div className="ranking-coverage"><strong>{eligibleScores.length}</strong><span>of {scores.length} eligible</span></div>
      <dl className="ranking-run-facts"><div><dt>Withheld</dt><dd>{withheldCount} names</dd></div><div><dt>Published</dt><dd>{formatPublicationTime(publishedAt)}</dd></div></dl>
      <div className="ranking-movers"><p className="eyebrow">SCORE MOVEMENT</p>{previousScoreDate && movers.length ? <><h3>Largest moves</h3><p className="ranking-movers-date">Compared with {formatResearchDate(previousScoreDate)}</p><ol>{movers.map(({ score, change }) => <li key={score.securityId}><Link href={`/stocks/${score.securityId}?date=${scoreDate}&from=rankings`}><div><strong>{score.ticker}</strong><span>{formatIssuerName(score.issuerName)}</span></div><b>{change > 0 ? "↑" : "↓"} {Math.abs(change)} pts</b></Link></li>)}</ol></> : <><h3>Largest moves</h3><p className="ranking-movers-empty">No prior comparable eligible run yet. Movement will appear after the next eligible update.</p></>}</div>
      <form className="rankings-date-form" action="/rankings"><label htmlFor="ranking-score-date">Score date<input id="ranking-score-date" name="date" type="date" defaultValue={scoreDate} required /></label><button type="submit">View date</button></form>
      <p>Only complete, dated inputs are ranked. Missing data is withheld rather than estimated.</p>
    </div>
    <div className="rankings-results">
      <ResearchBasket portfolio={portfolio} from="rankings" preview={previewBasket ? { scoreDate, positions: eligibleScores } : undefined} />
      <div className="section-heading">
        <div><p className="eyebrow">CURRENT ORDER</p><h2 id="rankings-list-title">Highest scores</h2></div>
      </div>
      <div className="ranking-column-labels" aria-hidden="true"><span>Rank</span><span>Company</span><span>Score</span></div>
      <ScoreList scores={visibleScores} from="rankings" />
      {visibleCount < eligibleScores.length && <button type="button" className="quiet-button rankings-show-more" onClick={() => setVisibleCount((current) => Math.min(current + initialVisibleCount, eligibleScores.length))}>Show 25 more <span>({eligibleScores.length - visibleCount} remaining)</span></button>}
    </div>
  </section>;
}
