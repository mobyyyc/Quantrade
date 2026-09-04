import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { DailyResearchSummary } from "@/components/daily-research-summary";
import { DailyUpdateControl } from "@/components/daily-update-control";
import { WatchlistPreview } from "@/components/watchlist-preview";
import { TodayRankingStream } from "@/components/today-ranking-stream";
import { ResearchBasket } from "@/components/research-basket";
import { formatResearchDate, formatScore } from "@/lib/format";
import { getDailyOperationsStatus, getLatestDatedScores, getLatestPaperPortfolio, getPreviousDatedScores, getTodayFilingSummary, ResearchReadModelError } from "@/lib/research-read-model";

export const dynamic = "force-dynamic";
const TODAY_RANKING_PREVIEW_LIMIT = 20;

export default async function Home() {
  let latest: Awaited<ReturnType<typeof getLatestDatedScores>> = null;
  let portfolio: Awaited<ReturnType<typeof getLatestPaperPortfolio>> = null;
  let previous: Awaited<ReturnType<typeof getPreviousDatedScores>> = null;
  let filingSummary: Awaited<ReturnType<typeof getTodayFilingSummary>> = { filingCount: 0 };
  let operations: Awaited<ReturnType<typeof getDailyOperationsStatus>> = {};
  let unavailable = false;
  try {
    [latest, portfolio, operations] = await Promise.all([
      getLatestDatedScores(),
      getLatestPaperPortfolio(),
      getDailyOperationsStatus(),
    ]);
    if (latest) {
      [previous, filingSummary] = await Promise.all([
        getPreviousDatedScores(latest.scoreDate),
        getTodayFilingSummary(latest.scoreDate),
      ]);
    }
  } catch (error) {
    unavailable = error instanceof ResearchReadModelError;
  }
  const lead = latest?.scores.find((score) => score.eligible);
  const eligibleScores = latest?.scores.filter((score) => score.eligible) ?? [];
  const rankingPreviewScores = eligibleScores.slice(0, TODAY_RANKING_PREVIEW_LIMIT).map((score) => ({
    scoreSnapshotId: score.scoreSnapshotId,
    securityId: score.securityId,
    issuerName: score.issuerName,
    ticker: score.ticker,
    scoreDate: score.scoreDate,
    score: score.score,
    rank: score.rank,
  }));
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
          <DailyResearchSummary
            scores={latest.scores}
            scoreDate={latest.scoreDate}
            previousScores={previous?.scores ?? []}
            previousScoreDate={previous?.scoreDate}
            filingCount={filingSummary.filingCount}
            filingSinceDate={filingSummary.sinceScoreDate}
            portfolio={portfolio}
            operations={operations}
          />
          <div className="today-grid">
            <section className="content-section today-candidates">
              <div className="section-heading"><div><p className="eyebrow">TOP RANKED</p><h2>Highest scores</h2></div>{lead && <Link href={`/rankings?date=${latest.scoreDate}`} className="text-link">View rankings</Link>}</div>
              {lead ? <TodayRankingStream scores={rankingPreviewScores} /> : <p className="empty-inline">No companies met every required quality condition on {formatResearchDate(latest.scoreDate)}.</p>}
              {lead ? <ResearchBasket portfolio={portfolio} from="today" /> : null}
            </section>
            <WatchlistPreview scoreDate={latest.scoreDate} />
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
