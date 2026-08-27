import Link from "next/link";
import { formatIssuerName, formatRelativeReturn, formatResearchDate, formatScore } from "@/lib/format";
import type { DatedScore } from "@/lib/research-read-model";

const BASKET_SIZE = 20;

function predictionDirection(value: string | number | undefined): "positive-change" | "negative-change" | undefined {
  if (value === undefined) return undefined;
  const prediction = Number(value);
  if (prediction > 0) return "positive-change";
  if (prediction < 0) return "negative-change";
  return undefined;
}

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
  const predictions = positions.flatMap((score) => score.predictedBenchmarkRelativeReturn ? [Number(score.predictedBenchmarkRelativeReturn)] : []);
  const basketPrediction = predictions.length === positions.length
    ? predictions.reduce((total, prediction) => total + prediction, 0) / predictions.length
    : undefined;
  const titleId = `${from}-research-basket-title`;

  return (
    <section className="research-basket" aria-labelledby={titleId}>
      <div className="research-basket-heading">
        <div>
          <p className="eyebrow">MODEL BASKET</p>
          <h2 id={titleId}>20-session research basket</h2>
        </div>
        <div className="research-basket-summary">
          {basketPrediction === undefined ? <span>Estimate unavailable</span> : <><span>Estimated basket return vs SPY</span><strong className={predictionDirection(basketPrediction)}>{formatRelativeReturn(basketPrediction)}</strong></>}
          <small>20 trading sessions</small>
        </div>
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
              aria-label={`${score.ticker}, rank ${score.rank}, score ${formatScore(score.score)} out of 100, ${score.predictedBenchmarkRelativeReturn ? `${formatRelativeReturn(score.predictedBenchmarkRelativeReturn)} estimated return versus SPY` : "estimated return unavailable"}, ${weight}% model weight`}
            >
              <span className="research-basket-position">{score.rank}</span>
              <span className="research-basket-company">
                <strong>{score.ticker}</strong>
                <span>{formatIssuerName(score.issuerName)}</span>
              </span>
              <span className="research-basket-prediction">
                <strong className={predictionDirection(score.predictedBenchmarkRelativeReturn)}>{score.predictedBenchmarkRelativeReturn ? formatRelativeReturn(score.predictedBenchmarkRelativeReturn) : "Unavailable"}</strong>
                <small>est. vs SPY</small>
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
