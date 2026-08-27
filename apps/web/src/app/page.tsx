import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { DailyUpdateControl } from "@/components/daily-update-control";
import { WatchlistPreview } from "@/components/watchlist-preview";
import { TodayRankingStream } from "@/components/today-ranking-stream";
import { formatIssuerName, formatResearchDate, formatScore, formatTorontoTime } from "@/lib/format";
import { getLatestDatedScores, getTodayFilingActivity, ResearchReadModelError } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";

export default async function Home() {
  let latest: Awaited<ReturnType<typeof getLatestDatedScores>> = null;
  let filingActivity: Awaited<ReturnType<typeof getTodayFilingActivity>> = [];
  let unavailable = false;
  try {
    latest = await getLatestDatedScores();
    filingActivity = latest ? await getTodayFilingActivity(latest.scoreDate) : [];
  } catch (error) {
    unavailable = error instanceof ResearchReadModelError;
  }
  const lead = latest?.scores.find((score) => score.eligible);
  const eligibleScores = latest?.scores.filter((score) => score.eligible) ?? [];
  return (
    <AppShell current="/">
      <section className="page-intro">
        <p className="eyebrow">TODAY</p>
        <h1>{latest ? `Research for ${formatResearchDate(latest.scoreDate)}.` : "Your research is waiting."}</h1>
        <p className="lede">{latest ? "Published research context, ready for inspection." : "Start with the current evidence when the next dated run is published."}</p>
      </section>
      {latest ? (
        <>
          {lead ? <section className="quant-view" aria-labelledby="quant-view-title">
              <div>
                <p className="eyebrow">LEAD RESEARCH CANDIDATE</p>
                <h2 id="quant-view-title">{lead.ticker}</h2>
                <p className="anchor-score">{formatScore(lead.score)}<span>/100</span></p>
                <p className="quiet-copy">Rank {lead.rank} of {eligibleScores.length} eligible names. {lead.signal} research score, Tier {lead.dataCapabilityTier} data.</p>
              </div>
              <Link href={`/stocks/${lead.securityId}?date=${lead.scoreDate}&from=today`} className="primary-link">View evidence</Link>
            </section> : <section className="today-run-state" aria-labelledby="today-run-state-title">
              <div><p className="eyebrow">DAILY UPDATE COMPLETE</p><h2 id="today-run-state-title">No eligible scores in this run.</h2></div>
              <p>A dated score snapshot was created, but no company passed every required market, filing, and sector-data quality gate. Quantrade does not estimate a score when an input is missing.</p>
              <Link href="/research" className="text-link">Review research limits</Link>
            </section>}
          <div className="today-grid">
            <section className="content-section today-candidates">
              <div className="section-heading"><div><p className="eyebrow">TOP RANKED</p><h2>Highest scores</h2></div>{lead && <Link href={`/rankings?date=${latest.scoreDate}`} className="text-link">View rankings</Link>}</div>
              {lead ? <TodayRankingStream scores={eligibleScores} /> : <p className="empty-inline">No companies met every required quality condition on {formatResearchDate(latest.scoreDate)}.</p>}
            </section>
            <WatchlistPreview scores={latest.scores} scoreDate={latest.scoreDate} />
          </div>
          <section className="content-section filing-activity" aria-labelledby="filing-activity-title">
            <div className="section-heading">
              <div><p className="eyebrow">MARKET ACTIVITY</p><h2 id="filing-activity-title">Today’s filings</h2></div>
              <p className="section-context">SEC documents accepted on {formatResearchDate(latest.scoreDate)}.</p>
            </div>
            {filingActivity.length ? <ul className="filing-activity-list">
              {filingActivity.map((activity) => {
                const primaryForm = activity.forms.includes("10-Q") ? "10-Q" : activity.forms.includes("10-K") ? "10-K" : activity.forms.includes("8-K") ? "8-K" : activity.forms[0] ?? "SEC filing";
                const label = activity.filingCount === 1
                  ? `${primaryForm} filed`
                  : `${activity.filingCount} SEC filings`;
                return <li key={activity.securityId}>
                  <Link href={`/stocks/${activity.securityId}?date=${latest.scoreDate}&from=today`} className="filing-activity-link" aria-label={`Open ${activity.ticker}. ${label}, accepted ${formatTorontoTime(activity.latestAcceptedAt)}.`}>
                    <div className="filing-activity-identity"><strong>{activity.ticker}</strong><span>{formatIssuerName(activity.issuerName)}</span></div>
                    <div className="filing-activity-detail"><strong>{label}</strong><span>{activity.forms.join(" · ")} · accepted {formatTorontoTime(activity.latestAcceptedAt)}</span></div>
                  </Link>
                </li>;
              })}
            </ul> : <p className="empty-inline">No SEC filings from this research universe were accepted today.</p>}
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
      <DailyUpdateControl />
    </AppShell>
  );
}
