import Link from "next/link";
import { formatIssuerName, formatRelativeReturn, formatResearchDate, formatScore } from "@/lib/format";
import type { PaperPortfolio } from "@/lib/research-read-model";

const BASKET_SIZE = 20;

function predictionDirection(value: string | number | undefined): "positive-change" | "negative-change" | undefined {
  if (value === undefined) return undefined;
  const prediction = Number(value);
  if (prediction > 0) return "positive-change";
  if (prediction < 0) return "negative-change";
  return undefined;
}

export function ResearchBasket({
  portfolio,
  from,
}: {
  portfolio: PaperPortfolio | null;
  from: "today" | "rankings";
}) {
  const titleId = `${from}-research-basket-title`;
  if (!portfolio) {
    return (
      <section className="research-basket research-basket-pending" aria-labelledby={titleId}>
        <div>
          <p className="eyebrow">MONTHLY MODEL PORTFOLIO</p>
          <h2 id={titleId}>Awaiting the next formation.</h2>
        </div>
        <p>No official model portfolio is active yet. It will be fixed from the final eligible score publication of a completed calendar month and recorded at the next regular-session open. Daily ranking changes do not rebalance it.</p>
      </section>
    );
  }

  const positions = portfolio.positions;
  const weight = 100 / BASKET_SIZE;
  const predictions = positions.flatMap((position) => position.predictedBenchmarkRelativeReturn ? [Number(position.predictedBenchmarkRelativeReturn)] : []);
  const basketPrediction = positions.length === BASKET_SIZE && predictions.length === positions.length
    ? predictions.reduce((total, prediction) => total + prediction, 0) / predictions.length
    : undefined;

  return (
    <section className="research-basket" aria-labelledby={titleId}>
      <div className="research-basket-heading">
        <div>
          <p className="eyebrow">MONTHLY MODEL PORTFOLIO</p>
          <h2 id={titleId}>Current 20-session research basket</h2>
        </div>
        <div className="research-basket-summary">
          {basketPrediction === undefined ? <span>Estimate unavailable</span> : <><span>Estimated basket return vs SPY</span><strong className={predictionDirection(basketPrediction)}>{formatRelativeReturn(basketPrediction)}</strong></>}
          <small>20 trading sessions</small>
        </div>
      </div>
      <div className="research-basket-context">
        <p>
          Formed from the model&apos;s top {BASKET_SIZE} eligible names on {formatResearchDate(portfolio.scoreDate)}, equally weighted at {weight}% each,
          then recorded at the next regular-session open on {formatResearchDate(portfolio.executionDate)}.
        </p>
        <p>Research only, not personalized investment advice.</p>
      </div>
      <ol className="research-basket-list">
        {positions.map((position) => (
          <li key={position.securityId}>
            <Link
              href={`/stocks/${position.securityId}?date=${portfolio.scoreDate}&from=${from}`}
              aria-label={`${position.ticker}, formation rank ${position.rank}, score ${formatScore(position.score)} out of 100, ${position.predictedBenchmarkRelativeReturn ? `${formatRelativeReturn(position.predictedBenchmarkRelativeReturn)} estimated return versus SPY` : "estimated return unavailable"}, ${weight}% model weight`}
            >
              <span className="research-basket-position">{position.rank}</span>
              <span className="research-basket-company">
                <strong>{position.ticker}</strong>
                <span>{formatIssuerName(position.issuerName)}</span>
              </span>
              <span className="research-basket-prediction">
                <strong className={predictionDirection(position.predictedBenchmarkRelativeReturn)}>{position.predictedBenchmarkRelativeReturn ? formatRelativeReturn(position.predictedBenchmarkRelativeReturn) : "Unavailable"}</strong>
                <small>est. vs SPY</small>
              </span>
              <span className="research-basket-score">{formatScore(position.score)}<small>/100</small></span>
              <span className="research-basket-weight">{weight}%</span>
            </Link>
          </li>
        ))}
      </ol>
      <p className="research-basket-note">
        This basket stays fixed until the next scheduled monthly formation. Daily rankings are research context only and do not change its holdings.
      </p>
    </section>
  );
}
