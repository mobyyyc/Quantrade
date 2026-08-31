import Link from "next/link";
import { formatIssuerName, formatRelativeReturn, formatResearchDate, formatScore } from "@/lib/format";
import type { DatedScore, PaperPortfolio, PreviousPaperPortfolioResult } from "@/lib/research-read-model";

const BASKET_SIZE = 20;

function returnDirection(value: string | number | undefined): "positive-change" | "negative-change" | undefined {
  if (value === undefined) return undefined;
  const prediction = Number(value);
  if (prediction > 0) return "positive-change";
  if (prediction < 0) return "negative-change";
  return undefined;
}

function PreviousBasketResult({ result }: { result?: PreviousPaperPortfolioResult }) {
  if (!result) {
    return (
      <div className="research-basket-result">
        <span>Previous basket result</span>
        <strong>Unavailable</strong>
        <small>No earlier official monthly basket.</small>
      </div>
    );
  }

  if (result.status === "pending") {
    return (
      <div className="research-basket-result">
        <span>Previous basket result</span>
        <strong>Pending</strong>
        <small>Formed {formatResearchDate(result.scoreDate)}. Waiting for its 20th market close.</small>
      </div>
    );
  }

  if (result.status === "withheld" || result.portfolioReturn === undefined || result.benchmarkReturn === undefined || result.benchmarkRelativeReturn === undefined) {
    return (
      <div className="research-basket-result">
        <span>Previous basket result</span>
        <strong>Unavailable</strong>
        <small>{result.unavailableReason ?? "The 20-session comparison did not pass data-quality checks."}</small>
      </div>
    );
  }

  const relativeReturn = Number(result.benchmarkRelativeReturn);
  const difference = `${relativeReturn >= 0 ? "+" : "−"}${(Math.abs(relativeReturn) * 100).toFixed(2)} pp`;

  return (
    <div className="research-basket-result">
      <span>Previous basket result</span>
      <strong className="research-basket-comparison">
        <span className={returnDirection(relativeReturn)}>{difference}</span>
        <span>vs SPY</span>
      </strong>
      <dl>
        <div><dt>Basket</dt><dd className={returnDirection(result.portfolioReturn)}>{formatRelativeReturn(result.portfolioReturn)}</dd></div>
        <div><dt>SPY</dt><dd className={returnDirection(result.benchmarkReturn)}>{formatRelativeReturn(result.benchmarkReturn)}</dd></div>
      </dl>
      <small>20 sessions ending {formatResearchDate(result.outcomeDate ?? "")}</small>
    </div>
  );
}

export function ResearchBasket({
  portfolio,
  from,
  preview,
}: {
  portfolio: PaperPortfolio | null;
  from: "today" | "rankings";
  preview?: {
    scoreDate: string;
    positions: DatedScore[];
  };
}) {
  const titleId = `${from}-research-basket-title`;
  if (preview) {
    const positions = preview.positions.slice(0, BASKET_SIZE);
    const weight = 100 / BASKET_SIZE;
    return (
      <section className="research-basket research-basket-preview" aria-labelledby={titleId}>
        <div className="research-basket-heading">
          <div>
            <div className="research-basket-preview-label">
              <p className="eyebrow">SIMULATED MONTHLY PORTFOLIO</p>
              <span>SCREENSHOT PREVIEW</span>
            </div>
            <h2 id={titleId}>Current Top 20 research basket</h2>
          </div>
          <div className="research-basket-preview-summary" aria-label={`${positions.length} companies at ${weight}% model weight each`}>
            <strong>{positions.length}</strong>
            <span>companies · {weight}% each</span>
          </div>
        </div>
        <div className="research-basket-context">
          <p>
            Simulated from the active model&apos;s top {positions.length} eligible names on {formatResearchDate(preview.scoreDate)}.
            This preview shows how the next monthly basket would look if it formed from the current ranking.
          </p>
          <p>Preview only, no official performance record.</p>
        </div>
        <ol className="research-basket-list">
          {positions.map((position, index) => (
            <li key={position.securityId}>
              <Link
                href={`/stocks/${position.securityId}?date=${preview.scoreDate}&from=${from}`}
                aria-label={`${position.ticker}, preview rank ${index + 1}, score ${formatScore(position.score)} out of 100, ${weight}% model weight`}
              >
                <span className="research-basket-position">{index + 1}</span>
                <span className="research-basket-company">
                  <strong>{position.ticker}</strong>
                  <span>{formatIssuerName(position.issuerName)}</span>
                </span>
                <span className="research-basket-score">{formatScore(position.score)}<small>/100</small></span>
                <span className="research-basket-weight">{weight}%</span>
              </Link>
            </li>
          ))}
        </ol>
        <p className="research-basket-note">
          The official portfolio still forms only from the final eligible ranking of a completed calendar month and is recorded at the next regular-session open.
        </p>
      </section>
    );
  }
  if (!portfolio) {
    return (
      <section className="research-basket research-basket-pending" aria-labelledby={titleId}>
        <div>
          <p className="eyebrow">MONTHLY MODEL PORTFOLIO</p>
          <h2 id={titleId}>Awaiting the next formation.</h2>
        </div>
        <div>
          <p>No official model portfolio is active yet. It will be fixed from the final eligible score publication of a completed calendar month and recorded at the next regular-session open. Daily ranking changes do not rebalance it.</p>
          <PreviousBasketResult />
        </div>
      </section>
    );
  }

  const positions = portfolio.positions;
  const weight = 100 / BASKET_SIZE;
  return (
    <section className="research-basket" aria-labelledby={titleId}>
      <div className="research-basket-heading">
        <div>
          <p className="eyebrow">MONTHLY MODEL PORTFOLIO</p>
          <h2 id={titleId}>Current 20-session research basket</h2>
        </div>
        <PreviousBasketResult result={portfolio.previousResult} />
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
              aria-label={`${position.ticker}, formation rank ${position.rank}, score ${formatScore(position.score)} out of 100, ${weight}% model weight`}
            >
              <span className="research-basket-position">{position.rank}</span>
              <span className="research-basket-company">
                <strong>{position.ticker}</strong>
                <span>{formatIssuerName(position.issuerName)}</span>
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
