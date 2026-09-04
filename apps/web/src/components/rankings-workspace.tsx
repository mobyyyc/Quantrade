"use client";

import { useState } from "react";
import Link from "next/link";
import { ScoreList, type ScoreListItem } from "@/components/score-list";
import { ResearchBasket } from "@/components/research-basket";
import { formatIssuerName, formatPublicationTime, formatResearchDate } from "@/lib/format";
import type { DatedScore, PaperPortfolio } from "@/lib/research-read-model";

const initialVisibleCount = 25;
const movementListLimit = 5;
export type RankingWorkspaceScore = ScoreListItem & Pick<DatedScore, "eligible" | "publishedAt">;

function formatPointChange(value: number) {
  const absolute = Math.abs(value);
  const formatted = absolute.toFixed(1).replace(/\.0$/, "");
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${formatted} pts`;
}

function MovementCompany({
  score,
  scoreDate,
  detail,
  value,
}: {
  score: RankingWorkspaceScore;
  scoreDate: string;
  detail: string;
  value: string;
}) {
  return (
    <li>
      <Link href={`/stocks/${score.securityId}?date=${scoreDate}&from=rankings`}>
        <span className="ranking-movement-company">
          <strong>{score.ticker}</strong>
          <small>{formatIssuerName(score.issuerName)}</small>
        </span>
        <span className="ranking-movement-value"><strong>{value}</strong><small>{detail}</small></span>
      </Link>
    </li>
  );
}

function DailyRankingMovement({
  scores,
  previousScores,
  scoreDate,
  previousScoreDate,
  portfolio,
}: {
  scores: RankingWorkspaceScore[];
  previousScores: RankingWorkspaceScore[];
  scoreDate: string;
  previousScoreDate?: string;
  portfolio: PaperPortfolio | null;
}) {
  const eligibleScores = scores.filter((score) => score.eligible && score.rank !== undefined);
  const eligiblePreviousScores = previousScores.filter((score) => score.eligible && score.rank !== undefined);
  const currentById = new Map(scores.map((score) => [score.securityId, score]));
  const previousById = new Map(previousScores.map((score) => [score.securityId, score]));
  const previousEligibleById = new Map(eligiblePreviousScores.map((score) => [score.securityId, score]));
  const comparableMoves = eligibleScores.flatMap((score) => {
    const previous = previousEligibleById.get(score.securityId);
    if (!previous || score.rank === undefined || previous.rank === undefined) return [];
    const rankChange = previous.rank - score.rank;
    const scoreChange = Number(score.score) - Number(previous.score);
    return rankChange || scoreChange ? [{ score, previous, rankChange, scoreChange }] : [];
  }).sort((left, right) => (
    Math.abs(right.rankChange) - Math.abs(left.rankChange)
    || Math.abs(right.scoreChange) - Math.abs(left.scoreChange)
  ));
  const currentTop = eligibleScores.filter((score) => (score.rank ?? Infinity) <= 20);
  const previousTop = eligiblePreviousScores.filter((score) => (score.rank ?? Infinity) <= 20);
  const currentTopIds = new Set(currentTop.map((score) => score.securityId));
  const previousTopIds = new Set(previousTop.map((score) => score.securityId));
  const entries = currentTop.filter((score) => !previousTopIds.has(score.securityId));
  const exits = previousTop.filter((score) => !currentTopIds.has(score.securityId));

  return (
    <section className="ranking-movement" aria-labelledby="ranking-movement-title">
      <div className="ranking-movement-heading">
        <div>
          <p className="eyebrow">DAILY MOVEMENT</p>
          <h2 id="ranking-movement-title">What changed in the ranking</h2>
          <p>{previousScoreDate ? `Compared with ${formatResearchDate(previousScoreDate)}.` : "A prior publication from the same model is required for comparison."}</p>
        </div>
        <div className="ranking-basket-status">
          <span>{portfolio ? "MONTHLY BASKET UNCHANGED" : "MONTHLY FORMATION"}</span>
          <strong>{portfolio ? "Official holdings remain fixed." : "No official basket is active yet."}</strong>
          <small>Daily score and rank movement does not create or rebalance a portfolio.</small>
          <Link href="/portfolio" className="text-link">View portfolio</Link>
        </div>
      </div>

      {previousScoreDate ? (
        <div className="ranking-movement-groups">
          <div className="ranking-movement-group">
            <div className="ranking-movement-group-heading"><h3>Largest moves</h3><span>Rank and score</span></div>
            {comparableMoves.length ? <ol>{comparableMoves.slice(0, movementListLimit).map(({ score, rankChange, scoreChange }) => (
              <MovementCompany
                key={score.securityId}
                score={score}
                scoreDate={scoreDate}
                value={rankChange === 0 ? "Rank unchanged" : `${rankChange > 0 ? "↑" : "↓"} ${Math.abs(rankChange)} ${Math.abs(rankChange) === 1 ? "rank" : "ranks"}`}
                detail={formatPointChange(scoreChange)}
              />
            ))}</ol> : <p className="ranking-movement-empty">No comparable eligible rank or score changed.</p>}
            {comparableMoves.length > movementListLimit && <p className="ranking-movement-more">{comparableMoves.length - movementListLimit} more changed names</p>}
          </div>

          <div className="ranking-movement-group">
            <div className="ranking-movement-group-heading"><h3>Entered Top 20</h3><span>{entries.length} names</span></div>
            {entries.length ? <ol>{entries.slice(0, movementListLimit).map((score) => {
              const previous = previousById.get(score.securityId);
              return <MovementCompany key={score.securityId} score={score} scoreDate={scoreDate} value={`Now #${score.rank}`} detail={previous?.eligible && previous.rank ? `from #${previous.rank}` : "newly eligible"} />;
            })}</ol> : <p className="ranking-movement-empty">No companies entered the Top 20.</p>}
            {entries.length > movementListLimit && <p className="ranking-movement-more">{entries.length - movementListLimit} more entries</p>}
          </div>

          <div className="ranking-movement-group">
            <div className="ranking-movement-group-heading"><h3>Exited Top 20</h3><span>{exits.length} names</span></div>
            {exits.length ? <ol>{exits.slice(0, movementListLimit).map((previous) => {
              const current = currentById.get(previous.securityId);
              return <MovementCompany key={previous.securityId} score={current ?? previous} scoreDate={scoreDate} value={`Was #${previous.rank}`} detail={current?.eligible && current.rank ? `now #${current.rank}` : "not eligible today"} />;
            })}</ol> : <p className="ranking-movement-empty">No companies exited the Top 20.</p>}
            {exits.length > movementListLimit && <p className="ranking-movement-more">{exits.length - movementListLimit} more exits</p>}
          </div>
        </div>
      ) : <p className="ranking-movement-empty ranking-movement-empty-wide">Movement will appear after this model completes another eligible daily publication.</p>}
    </section>
  );
}

export function RankingsWorkspace({ scores, scoreDate, previousScoreDate, previousScores, portfolio }: { scores: RankingWorkspaceScore[]; scoreDate: string; previousScoreDate?: string; previousScores: RankingWorkspaceScore[]; portfolio: PaperPortfolio | null }) {
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
      <ResearchBasket portfolio={portfolio} from="rankings" />
      <DailyRankingMovement scores={scores} previousScores={previousScores} scoreDate={scoreDate} previousScoreDate={previousScoreDate} portfolio={portfolio} />
      <div className="section-heading">
        <div><p className="eyebrow">CURRENT ORDER</p><h2 id="rankings-list-title">Highest scores</h2></div>
      </div>
      <div className="ranking-column-labels" aria-hidden="true"><span>Rank</span><span>Company</span><span>Score</span></div>
      <ScoreList scores={visibleScores} from="rankings" />
      {visibleCount < eligibleScores.length && <button type="button" className="quiet-button rankings-show-more" onClick={() => setVisibleCount((current) => Math.min(current + initialVisibleCount, eligibleScores.length))}>Show 25 more <span>({eligibleScores.length - visibleCount} remaining)</span></button>}
    </div>
  </section>;
}
