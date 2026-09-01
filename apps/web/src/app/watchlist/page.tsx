import { AppShell } from "@/components/app-shell";
import { WatchlistWorkspace } from "@/components/watchlist-workspace";
import { getLatestDatedScores, getPreviousDatedScores, ResearchReadModelError, type DatedScore } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";

export default async function WatchlistPage() {
  let scores: DatedScore[] = [];
  let previousScores: DatedScore[] = [];
  let scoreDate: string | undefined;
  let previousScoreDate: string | undefined;
  let unavailable = false;
  try {
    const latest = await getLatestDatedScores();
    scores = latest?.scores ?? [];
    scoreDate = latest?.scoreDate;
    if (scoreDate) {
      const previous = await getPreviousDatedScores(scoreDate);
      previousScores = previous?.scores ?? [];
      previousScoreDate = previous?.scoreDate;
    }
  } catch (error) {
    unavailable = error instanceof ResearchReadModelError;
  }

  return <AppShell current="/watchlist">
    <section className="page-intro compact"><p className="eyebrow">WATCHLIST</p><h1>Companies you want to revisit.</h1><p className="lede">Saved names stay here, with their latest dated research context when it is available.</p></section>
    {unavailable && <p className="inline-notice">Research data is unavailable. Saved names remain available, but their latest score cannot be shown.</p>}
    <WatchlistWorkspace scores={scores} scoreDate={scoreDate} previousScores={previousScores} previousScoreDate={previousScoreDate} />
  </AppShell>;
}
