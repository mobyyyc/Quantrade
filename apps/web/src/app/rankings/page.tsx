import { AppShell } from "@/components/app-shell";
import { ScoreList } from "@/components/score-list";
import { formatResearchDate } from "@/lib/format";
import { listDatedScores, ResearchReadModelError, type DatedScore } from "@/lib/research-read-model";

export default async function RankingsPage({ searchParams }: { searchParams: Promise<{ date?: string }> }) {
  const { date } = await searchParams;
  const validDate = date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : undefined;
  let scores: DatedScore[] = [];
  let unavailable = false;
  if (validDate) {
    try { scores = await listDatedScores(validDate); } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  }
  return <AppShell current="/rankings">
    <section className="page-intro compact"><p className="eyebrow">RANKINGS</p><h1>Open a short, dated research list.</h1><p className="lede">Scores are research context, not trade instructions.</p></section>
    <form className="date-form" action="/rankings"><label htmlFor="score-date">Score date</label><input id="score-date" name="date" type="date" defaultValue={validDate} required /><button type="submit">View date</button></form>
    {validDate ? <section className="content-section"><div className="section-heading"><div><p className="eyebrow">{formatResearchDate(validDate)}</p><h2>Published research scores</h2></div><span className="status-label">{scores.filter((score) => score.eligible).length} eligible</span></div>{unavailable ? <p className="empty-inline">Research data is not connected. No example scores are shown.</p> : <ScoreList scores={scores.filter((score) => score.eligible)} />}</section> : <section className="empty-state small"><h2>Select a published score date.</h2><p>Rankings stay tied to a specific end-of-day research run.</p></section>}
  </AppShell>;
}
