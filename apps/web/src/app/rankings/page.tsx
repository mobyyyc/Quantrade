import { AppShell } from "@/components/app-shell";
import { ResearchNotice } from "@/components/research-notice";
import { RankingsWorkspace } from "@/components/rankings-workspace";
import { formatResearchDate } from "@/lib/format";
import { getLatestDatedScores, listDatedScores, ResearchReadModelError, type DatedScore } from "@/lib/research-read-model";

export default async function RankingsPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const { date } = await searchParams;
  const validDate = date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : undefined;
  let scores: DatedScore[] = [];
  let scoreDate: string | undefined = validDate;
  let unavailable = false;
  try {
    if (validDate) scores = await listDatedScores(validDate);
    else {
      const latest = await getLatestDatedScores();
      scoreDate = latest?.scoreDate;
      scores = latest?.scores ?? [];
    }
  } catch (error) {
    unavailable = error instanceof ResearchReadModelError;
  }
  return <AppShell current="/rankings">
    <section className="page-intro compact"><p className="eyebrow">RANKED RESEARCH</p><h1>Start with the names worth inspecting.</h1><p className="lede">{scoreDate ? `Research scores for ${formatResearchDate(scoreDate)}. They are dated context, not trade instructions.` : "Research scores are published only after required inputs pass their data-quality gates."}</p></section>
    {unavailable ? <section className="empty-state small"><h2>Research data is not connected.</h2><p>Connect the normalized research database to view published rankings and manage your watchlist.</p></section> : scoreDate ? <><RankingsWorkspace scores={scores} scoreDate={scoreDate} /><form className="date-form date-form-secondary" action="/rankings"><label htmlFor="score-date">View another published date<input id="score-date" name="date" type="date" defaultValue={scoreDate} required /></label><button type="submit">View date</button></form></> : <section className="empty-state small"><h2>No research score has been published yet.</h2><p>Run a completed end-of-day research process before rankings can appear here.</p></section>}
    <ResearchNotice />
  </AppShell>;
}
