"use client";

import { useState } from "react";
import { ScoreList } from "@/components/score-list";
import { formatPublicationTime } from "@/lib/format";
import type { DatedScore } from "@/lib/research-read-model";

const initialVisibleCount = 25;

export function RankingsWorkspace({ scores, scoreDate }: { scores: DatedScore[]; scoreDate: string }) {
  const [visibleCount, setVisibleCount] = useState(initialVisibleCount);
  const eligibleScores = scores.filter((score) => score.eligible);
  const withheldCount = scores.length - eligibleScores.length;
  const publishedAt = scores.find((score) => score.publishedAt)?.publishedAt;
  const visibleScores = eligibleScores.slice(0, visibleCount);

  return <section className="rankings-layout" aria-labelledby="rankings-list-title">
    <div className="rankings-context" aria-label="Ranking context">
      <p className="eyebrow">PUBLISHED COVERAGE</p>
      <div className="ranking-coverage"><strong>{eligibleScores.length}</strong><span>of {scores.length} eligible</span></div>
      <dl className="ranking-run-facts"><div><dt>Withheld</dt><dd>{withheldCount} names</dd></div><div><dt>Published</dt><dd>{formatPublicationTime(publishedAt)}</dd></div></dl>
      <form className="rankings-date-form" action="/rankings"><label htmlFor="ranking-score-date">Score date<input id="ranking-score-date" name="date" type="date" defaultValue={scoreDate} required /></label><button type="submit">View date</button></form>
      <p>Only complete, dated inputs are ranked. Missing data is withheld rather than estimated.</p>
    </div>
    <div className="rankings-results">
      <div className="section-heading">
        <div><p className="eyebrow">CURRENT ORDER</p><h2 id="rankings-list-title">Highest scores</h2></div>
      </div>
      <div className="ranking-column-labels" aria-hidden="true"><span>Rank</span><span>Company</span><span>Score</span></div>
      <ScoreList scores={visibleScores} from="rankings" />
      {visibleCount < eligibleScores.length && <button type="button" className="quiet-button rankings-show-more" onClick={() => setVisibleCount((current) => Math.min(current + initialVisibleCount, eligibleScores.length))}>Show 25 more <span>({eligibleScores.length - visibleCount} remaining)</span></button>}
    </div>
  </section>;
}
