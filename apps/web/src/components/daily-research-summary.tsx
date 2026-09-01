import Link from "next/link";
import { formatResearchDate } from "@/lib/format";
import type { DailyOperationsStatus, DatedScore, PaperPortfolio } from "@/lib/research-read-model";

type RankMovement = {
  score: DatedScore;
  rankChange: number;
};

function largestRankMovements(scores: DatedScore[], previousScores: DatedScore[]): RankMovement[] {
  const previousEligibleById = new Map(
    previousScores
      .filter((score) => score.eligible && score.rank !== undefined)
      .map((score) => [score.securityId, score]),
  );

  return scores.flatMap((score) => {
    const previous = previousEligibleById.get(score.securityId);
    if (!score.eligible || score.rank === undefined || previous?.rank === undefined) return [];
    const rankChange = previous.rank - score.rank;
    return rankChange === 0 ? [] : [{ score, rankChange }];
  }).sort((left, right) => Math.abs(right.rankChange) - Math.abs(left.rankChange)).slice(0, 2);
}

function qualityStatus(
  scoreDate: string,
  withheldCount: number,
  operations: DailyOperationsStatus,
): { headline: string; detail: string } {
  const latestRun = operations.latestRun;
  if (latestRun?.status === "failed" && latestRun.scoreDate >= scoreDate) {
    return {
      headline: "Latest refresh needs attention",
      detail: "The last published scores remain intact.",
    };
  }
  if (
    operations.latestMarketSession
    && operations.latestBenchmarkSession
    && operations.latestMarketSession !== operations.latestBenchmarkSession
  ) {
    return {
      headline: "Price sources need review",
      detail: "Stock and SPY sessions are not aligned.",
    };
  }
  if (withheldCount > 0) {
    return {
      headline: `${withheldCount} ${withheldCount === 1 ? "name" : "names"} withheld`,
      detail: "Incomplete inputs were not estimated.",
    };
  }
  return { headline: "Checks passed", detail: "Every covered name was eligible." };
}

export function DailyResearchSummary({
  scores,
  scoreDate,
  previousScores,
  previousScoreDate,
  filingCount,
  filingSinceDate,
  portfolio,
  operations,
}: {
  scores: DatedScore[];
  scoreDate: string;
  previousScores: DatedScore[];
  previousScoreDate?: string;
  filingCount: number;
  filingSinceDate?: string;
  portfolio: PaperPortfolio | null;
  operations: DailyOperationsStatus;
}) {
  const eligibleScores = scores.filter((score) => score.eligible);
  const previousEligibleIds = new Set(previousScores.filter((score) => score.eligible).map((score) => score.securityId));
  const newlyEligibleCount = previousScoreDate
    ? eligibleScores.filter((score) => !previousEligibleIds.has(score.securityId)).length
    : undefined;
  const movements = previousScoreDate ? largestRankMovements(scores, previousScores) : [];
  const withheldCount = scores.length - eligibleScores.length;
  const quality = qualityStatus(scoreDate, withheldCount, operations);
  const rankingsHref = `/rankings?date=${scoreDate}`;

  return (
    <section className="daily-research-brief" aria-labelledby="daily-research-brief-title">
      <header className="daily-research-brief-heading">
        <div>
          <p className="eyebrow">DAILY BRIEFING</p>
          <h2 id="daily-research-brief-title">What changed in this publication</h2>
        </div>
        <p>Scores move daily. The official portfolio changes only at its scheduled monthly formation.</p>
      </header>

      <div className="daily-research-brief-grid">
        <div className="daily-research-brief-item">
          <span>New scores</span>
          <strong>{newlyEligibleCount === undefined ? "Awaiting comparison" : `${newlyEligibleCount} newly eligible`}</strong>
          <small>{previousScoreDate ? `Since ${formatResearchDate(previousScoreDate)}` : "A prior run from this model is required."}</small>
          <Link href={rankingsHref}>Review coverage</Link>
        </div>

        <div className="daily-research-brief-item daily-research-brief-movements">
          <span>Largest moves</span>
          {movements.length ? (
            <ul>
              {movements.map(({ score, rankChange }) => (
                <li key={score.securityId}>
                  <Link href={`/stocks/${score.securityId}?date=${scoreDate}&from=today`}>
                    <strong>{score.ticker}</strong>
                    <small>{rankChange > 0 ? "↑" : "↓"} {Math.abs(rankChange)} {Math.abs(rankChange) === 1 ? "rank" : "ranks"}</small>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <><strong>{previousScoreDate ? "No rank changes" : "Awaiting comparison"}</strong><small>{previousScoreDate ? "Eligible ranks were unchanged." : "Movement needs a prior comparable run."}</small></>
          )}
        </div>

        <div className="daily-research-brief-item">
          <span>Relevant filings</span>
          <strong>{filingCount} {filingCount === 1 ? "filing" : "filings"}</strong>
          <small>{filingSinceDate ? `Accepted after ${formatResearchDate(filingSinceDate)} through ${formatResearchDate(scoreDate)}.` : `Accepted by the SEC on ${formatResearchDate(scoreDate)}.`}</small>
        </div>

        <div className="daily-research-brief-item">
          <span>Portfolio</span>
          <strong>{portfolio ? `${portfolio.positions.length} holdings fixed` : "Awaiting formation"}</strong>
          <small>{portfolio ? `Formed ${formatResearchDate(portfolio.scoreDate)}.` : "Daily rankings do not create a basket."}</small>
          <Link href="/portfolio">View portfolio</Link>
        </div>

        <div className="daily-research-brief-item">
          <span>Data quality</span>
          <strong>{quality.headline}</strong>
          <small>{quality.detail}</small>
          <Link href="/research">Review operations</Link>
        </div>
      </div>
    </section>
  );
}
