import Link from "next/link";
import type { DatedScore } from "@/lib/research-read-model";
import { formatScore } from "@/lib/format";

export function ScoreList({ scores, limit }: { scores: DatedScore[]; limit?: number }) {
  const rows = limit ? scores.slice(0, limit) : scores;
  if (!rows.length) {
    return <p className="quiet-copy">No eligible research scores were published for this date.</p>;
  }
  return (
    <ol className="score-list">
      {rows.map((score) => (
        <li key={score.scoreSnapshotId} className="score-row">
          <span className="rank-number">{score.rank ?? "Unavailable"}</span>
          <div className="score-row-main">
            <Link
              href={`/stocks/${score.securityId}?date=${score.scoreDate}`}
              className="score-row-link"
              aria-label={`Open research detail for ${score.ticker}`}
            >
              <strong>{score.ticker}</strong>
              <span>{score.issuerName}</span>
            </Link>
            <span className="row-meta">{score.signal} research score</span>
          </div>
          <div className="score-row-value">
            <strong>{formatScore(score.score)}</strong>
            <span>of 100</span>
          </div>
        </li>
      ))}
    </ol>
  );
}
