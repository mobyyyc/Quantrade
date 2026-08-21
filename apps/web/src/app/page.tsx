import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { ResearchNotice } from "@/components/research-notice";
import { ScoreList } from "@/components/score-list";
import { formatResearchDate, formatScore } from "@/lib/format";
import { getLatestDatedScores, ResearchReadModelError } from "@/lib/research-read-model";

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
        <h1>One calm place to start your research.</h1>
        <p className="lede">Review the latest dated score run, then open the evidence behind a name.</p>
      </section>
      {lead && latest ? (
        <>
          <section className="quant-view" aria-labelledby="quant-view-title">
            <div>
              <p className="eyebrow">PUBLISHED {formatResearchDate(latest.scoreDate)}</p>
              <h2 id="quant-view-title">Research score</h2>
              <p className="anchor-score">{formatScore(lead.score)}<span>/100</span></p>
              <p className="quiet-copy">Rank {lead.rank} of {latest.scores.filter((score) => score.eligible).length} eligible names. Tier {lead.dataCapabilityTier} research data.</p>
            </div>
            <Link href={`/stocks/${lead.securityId}?date=${lead.scoreDate}`} className="primary-link">View evidence</Link>
          </section>
          <section className="content-section">
            <div className="section-heading"><div><p className="eyebrow">SHORTLIST</p><h2>Research candidates</h2></div><Link href={`/rankings?date=${latest.scoreDate}`} className="text-link">View all rankings</Link></div>
            <ScoreList scores={latest.scores.filter((score) => score.eligible)} limit={5} />
          </section>
        </>
      ) : (
        <section className="empty-state">
          <p className="eyebrow">RESEARCH STATUS</p>
          <h2>{unavailable ? "Research data is not connected yet." : "No research score has been published yet."}</h2>
          <p>{unavailable ? "Connect the normalized research database to view dated scores. Quantrade will not substitute example market data." : "A completed end-of-day run will appear here with its date, model context, and evidence."}</p>
          <Link href="/research" className="primary-link">Read methodology</Link>
        </section>
      )}
      <ResearchNotice />
    </AppShell>
  );
}
