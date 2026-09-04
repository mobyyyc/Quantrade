import Link from "next/link";
import type { DatedScore } from "@/lib/research-read-model";
import { formatIssuerName, formatScore } from "@/lib/format";

export type ScoreListItem = Pick<DatedScore,
  "scoreSnapshotId" | "securityId" | "issuerName" | "ticker" | "scoreDate" | "score" | "rank"
>;

export function ScoreList({ scores, limit, from = "rankings", variant = "default" }: { scores: ScoreListItem[]; limit?: number; from?: "today" | "rankings"; variant?: "default" | "today" }) {
  const rows = limit ? scores.slice(0, limit) : scores;
  if (!rows.length) {
    return <p className="quiet-copy">No eligible research scores were published for this date.</p>;
  }
  return (
    <ol className={`score-list${variant === "today" ? " score-list-today" : ""}`}>
      {rows.map((score) => (
        <li key={score.scoreSnapshotId} className="score-row">
          <Link
            href={`/stocks/${score.securityId}?date=${score.scoreDate}&from=${from}`}
            className="score-row-link"
            aria-label={`Open research detail for ${score.ticker}, score ${formatScore(score.score)} out of 100`}
          >
            <span className="rank-number">{score.rank ?? "Unavailable"}</span>
            <div className="score-row-main">
              <strong>{score.ticker}</strong>
              <span>{formatIssuerName(score.issuerName)}</span>
            </div>
            <div className="score-row-value"><span className="score-unit"><strong>{formatScore(score.score)}</strong><span>/100</span></span></div>
          </Link>
        </li>
      ))}
    </ol>
  );
}
