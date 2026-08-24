import { formatResearchDate, formatScore } from "@/lib/format";
import type { ScoreHistoryPoint } from "@/lib/research-read-model";

export function ScoreHistory({ points }: { points: ScoreHistoryPoint[] }) {
  const current = points.at(-1);
  const previous = points.at(-2);
  const change = current && previous ? Number(formatScore(current.score)) - Number(formatScore(previous.score)) : null;
  const direction = change === null || change === 0 ? "unchanged" : change > 0 ? "up" : "down";
  const directionCopy = change === null ? "No prior eligible run" : change === 0 ? "Unchanged from prior run" : `${change > 0 ? "↑" : "↓"} ${Math.abs(change).toFixed(0)} point${Math.abs(change) === 1 ? "" : "s"} from prior run`;

  return <section className="content-section score-history" aria-labelledby="score-history-title">
    <div className="section-heading"><div><p className="eyebrow">SCORE HISTORY</p><h2 id="score-history-title">Dated score movement</h2></div><span className={`score-history-change ${direction}`}>{directionCopy}</span></div>
    {current ? <><p className="score-history-context">Only eligible, published score runs are compared. The next eligible update will extend this record automatically.</p><ol className="score-history-list">{points.slice().reverse().map((point) => <li key={point.scoreDate}><time dateTime={point.scoreDate}>{formatResearchDate(point.scoreDate)}</time><span className="score-unit"><strong>{formatScore(point.score)}</strong><span>/100</span></span><small>{point.rank ? `Rank ${point.rank}` : "Rank unavailable"}</small></li>)}</ol></> : <p className="empty-inline">A score history will appear after this company receives its first eligible published score.</p>}
  </section>;
}
