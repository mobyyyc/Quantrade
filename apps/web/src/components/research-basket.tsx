import Link from "next/link";
import { formatIssuerName, formatResearchDate, formatScore } from "@/lib/format";
import type { DatedScore } from "@/lib/research-read-model";

const BASKET_SIZE = 20;

export function ResearchBasket({
  scores,
  scoreDate,
  from,
}: {
  scores: DatedScore[];
  scoreDate: string;
  from: "today" | "rankings";
}) {
  const positions = scores.filter((score) => score.eligible).slice(0, BASKET_SIZE);
  if (positions.length < BASKET_SIZE) return null;

  const weight = 100 / positions.length;
  const titleId = `${from}-research-basket-title`;

  return (
    <section className="research-basket" aria-labelledby={titleId}>
      <div className="research-basket-heading">
        <div>
          <p className="eyebrow">MODEL BASKET</p>
          <h2 id={titleId}>20-session research basket</h2>
        </div>
        <span className="research-basket-horizon">Review after 20 trading sessions</span>
      </div>
      <div className="research-basket-context">
        <p>
          The model&apos;s top {BASKET_SIZE} eligible names for {formatResearchDate(scoreDate)}, equally weighted at {weight}% each.
          This is the same portfolio size used by the evaluated research protocol.
        </p>
        <p>Research only, not personalized investment advice.</p>
      </div>
      <ol className="research-basket-list">
        {positions.map((score) => (
          <li key={score.scoreSnapshotId}>
            <Link
              href={`/stocks/${score.securityId}?date=${score.scoreDate}&from=${from}`}
              aria-label={`${score.ticker}, rank ${score.rank}, score ${formatScore(score.score)} out of 100, ${weight}% model weight`}
            >
              <span className="research-basket-position">{score.rank}</span>
              <span className="research-basket-company">
                <strong>{score.ticker}</strong>
                <span>{formatIssuerName(score.issuerName)}</span>
              </span>
              <span className="research-basket-score">{formatScore(score.score)}<small>/100</small></span>
              <span className="research-basket-weight">{weight}%</span>
            </Link>
          </li>
        ))}
      </ol>
      <p className="research-basket-note">
        Formation is based on dated scores. Any real execution would occur at the next regular-session open, so prices may differ.
      </p>
    </section>
  );
}
