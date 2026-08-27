import Link from "next/link";
import { formatIssuerName, formatRelativeReturn, formatResearchDate, formatScore } from "@/lib/format";
import type { PaperPortfolio, PreviousPaperPortfolioResult } from "@/lib/research-read-model";

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
  const isPreview = result.previewKind === "current_top_20_retrospective";

  return (
    <div className={`research-basket-result${isPreview ? " research-basket-result-preview" : ""}`}>
      <span className="research-basket-result-label">
        Previous basket result
        {isPreview ? <b>UI preview</b> : null}
      </span>
      <strong className="research-basket-comparison">
        <span className={returnDirection(relativeReturn)}>{difference}</span>
        <span>vs SPY</span>
      </strong>
      <dl>
        <div><dt>Basket</dt><dd className={returnDirection(result.portfolioReturn)}>{formatRelativeReturn(result.portfolioReturn)}</dd></div>
        <div><dt>SPY</dt><dd className={returnDirection(result.benchmarkReturn)}>{formatRelativeReturn(result.benchmarkReturn)}</dd></div>
      </dl>
      <small>
        {isPreview
          ? `Retrospective layout sample using the current top 20 selected on ${formatResearchDate(result.scoreDate)} and their preceding 20-session prices. This is look-ahead-biased, not official performance.`
          : `20 sessions ending ${formatResearchDate(result.outcomeDate ?? "")}`}
      </small>
    </div>
  );
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
        <div>
          <p>No official model portfolio is active yet. It will be fixed from the final eligible score publication of a completed calendar month and recorded at the next regular-session open. Daily ranking changes do not rebalance it.</p>
          <PreviousBasketResult />
        </div>
      </section>
    );
  }

  const positions = portfolio.positions;
  const weight = 100 / BASKET_SIZE;
  const isPreview = portfolio.previewKind === "current_top_20_retrospective";
  return (
    <section className={`research-basket${isPreview ? " research-basket-preview" : ""}`} aria-labelledby={titleId}>
      <div className="research-basket-heading">
        <div>
          <p className="eyebrow">
            MONTHLY MODEL PORTFOLIO
            {isPreview ? <span className="research-basket-preview-tag">UI PREVIEW</span> : null}
          </p>
          <h2 id={titleId}>{isPreview ? "Current top 20, shown as a prior basket" : "Current 20-session research basket"}</h2>
        </div>
        <PreviousBasketResult result={portfolio.previousResult} />
      </div>
      <div className="research-basket-context">
        {isPreview ? (
          <p>
            For layout inspection only. This applies the top {BASKET_SIZE} names selected on {formatResearchDate(portfolio.scoreDate)} to the preceding 20-session price window, equally weighted at {weight}% each.
          </p>
        ) : (
          <p>
            Formed from the model&apos;s top {BASKET_SIZE} eligible names on {formatResearchDate(portfolio.scoreDate)}, equally weighted at {weight}% each,
            then recorded at the next regular-session open on {formatResearchDate(portfolio.executionDate)}.
          </p>
        )}
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
        {isPreview
          ? "Preview data is calculated in memory and is not saved as an official portfolio or performance record. It disappears when a real monthly basket is available."
          : "This basket stays fixed until the next scheduled monthly formation. Daily rankings are research context only and do not change its holdings."}
      </p>
    </section>
  );
}
