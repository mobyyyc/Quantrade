import { AppShell } from "@/components/app-shell";
import { RankingsWorkspace } from "@/components/rankings-workspace";
import { formatResearchDate } from "@/lib/format";
import { getLatestDatedScores, getLatestPaperPortfolio, getPreviousDatedScores, listDatedScores, ResearchReadModelError, type DatedScore, type PaperPortfolio } from "@/lib/research-read-model";

export default async function RankingsPage({ searchParams }: { searchParams: Promise<{ date?: string; basketPreview?: string }> }) {
  const { date, basketPreview } = await searchParams;
  const validDate = date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : undefined;
  let scores: DatedScore[] = [];
  let scoreDate: string | undefined = validDate;
  let previousScoreDate: string | undefined;
  let previousScores: DatedScore[] = [];
  let portfolio: PaperPortfolio | null = null;
  let unavailable = false;
  try {
    if (validDate) scores = await listDatedScores(validDate);
    else {
      const latest = await getLatestDatedScores();
      scoreDate = latest?.scoreDate;
      scores = latest?.scores ?? [];
    }
    if (scoreDate) {
      const [previous, datedPortfolio] = await Promise.all([
        getPreviousDatedScores(scoreDate),
        getLatestPaperPortfolio(scoreDate),
      ]);
      previousScoreDate = previous?.scoreDate;
      previousScores = previous?.scores ?? [];
      portfolio = datedPortfolio;
    }
  } catch (error) {
    unavailable = error instanceof ResearchReadModelError;
  }
  return <AppShell current="/rankings">
    <section className="page-intro compact"><p className="eyebrow">RANKINGS</p><h1>Highest research scores.</h1><p className="lede">{scoreDate ? `Research scores for ${formatResearchDate(scoreDate)}. They are dated context, not trade instructions.` : "Research scores are published only after required inputs pass their data-quality gates."}</p></section>
    {unavailable ? <section className="empty-state small"><h2>Research data is not connected.</h2><p>Connect the normalized research database to view published rankings.</p></section> : scoreDate ? <RankingsWorkspace scores={scores} scoreDate={scoreDate} previousScoreDate={previousScoreDate} previousScores={previousScores} portfolio={portfolio} previewBasket={basketPreview === "1"} /> : <section className="empty-state small"><h2>No research score has been published yet.</h2><p>Run a completed end-of-day research process before rankings can appear here.</p></section>}
  </AppShell>;
}
