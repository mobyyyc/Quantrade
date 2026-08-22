import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { ScoreList } from "@/components/score-list";
import { DailyUpdateControl } from "@/components/daily-update-control";
import { WatchlistPreview } from "@/components/watchlist-preview";
import { formatResearchDate, formatScore } from "@/lib/format";
import { getLatestDatedScores, ResearchReadModelError } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";

export default async function Home() {
  let latest: Awaited<ReturnType<typeof getLatestDatedScores>> = null;
  let unavailable = false;
  try {
    latest = await getLatestDatedScores();
  } catch (error) {
    unavailable = error instanceof ResearchReadModelError;
  }
  const lead = latest?.scores.find((score) => score.eligible);
  return (
    <AppShell current="/">
      <section className="page-intro">
        <p className="eyebrow">TODAY</p>
        <h1>{latest ? `Research for ${formatResearchDate(latest.scoreDate)}.` : "Your research is waiting."}</h1>
        <p className="lede">{latest ? "Published research context, ready for inspection." : "Start with the current evidence when the next dated run is published."}</p>
      </section>
      {lead && latest ? (
        <>
          <section className="quant-view" aria-labelledby="quant-view-title">
            <div>
              <p className="eyebrow">LEAD RESEARCH CANDIDATE</p>
              <h2 id="quant-view-title">{lead.ticker}</h2>
              <p className="anchor-score">{formatScore(lead.score)}<span>/100</span></p>
              <p className="quiet-copy">Rank {lead.rank} of {latest.scores.filter((score) => score.eligible).length} eligible names. {lead.signal} research score, Tier {lead.dataCapabilityTier} data.</p>
            </div>
            <Link href={`/stocks/${lead.securityId}?date=${lead.scoreDate}&from=today`} className="primary-link">View evidence</Link>
          </section>
          <div className="today-grid">
            <section className="content-section today-candidates">
              <div className="section-heading"><div><p className="eyebrow">SHORTLIST</p><h2>Research candidates</h2></div><Link href={`/rankings?date=${latest.scoreDate}`} className="text-link">View rankings</Link></div>
              <ScoreList scores={latest.scores.filter((score) => score.eligible)} limit={5} from="today" />
            </section>
            <WatchlistPreview scores={latest.scores} scoreDate={latest.scoreDate} />
          </div>
        </>
      ) : (
        <section className="empty-state">
          <p className="eyebrow">RESEARCH STATUS</p>
          <h2>{unavailable ? "Research data is not connected yet." : "No research score has been published yet."}</h2>
          <p>{unavailable ? "Connect the normalized research database to view dated scores. Quantrade will not substitute example market data." : "A completed end-of-day run will appear here with its date, model context, and evidence."}</p>
          <Link href="/research" className="primary-link">Read methodology</Link>
        </section>
      )}
      <DailyUpdateControl />
    </AppShell>
  );
}
