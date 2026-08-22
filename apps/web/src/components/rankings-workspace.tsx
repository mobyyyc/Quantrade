import { ScoreList } from "@/components/score-list";
import type { DatedScore } from "@/lib/research-read-model";

export function RankingsWorkspace({ scores }: { scores: DatedScore[] }) {
  const eligibleScores = scores.filter((score) => score.eligible);

  return <section className="rankings-layout" aria-labelledby="rankings-list-title">
    <div className="rankings-context" aria-label="Ranking context">
      <p className="eyebrow">PUBLISHED UNIVERSE</p>
      <strong>{eligibleScores.length}</strong>
      <span>eligible names</span>
      <p>Scores are a dated research starting point, not trade instructions.</p>
    </div>
    <div className="rankings-results">
      <div className="section-heading">
        <div><p className="eyebrow">CURRENT ORDER</p><h2 id="rankings-list-title">Research candidates</h2></div>
      </div>
      <ScoreList scores={eligibleScores} from="rankings" />
    </div>
  </section>;
}
