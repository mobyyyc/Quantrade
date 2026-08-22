import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { formatResearchDate } from "@/lib/format";
import { getLatestPaperPortfolio, getModelCard, ResearchReadModelError } from "@/lib/research-read-model";

export default async function ResearchPage() {
  let card = null;
  let portfolio = null;
  let unavailable = false;
  try {
    card = await getModelCard("baseline_equal_weight_v1");
    portfolio = await getLatestPaperPortfolio();
  } catch (error) { unavailable = error instanceof ResearchReadModelError; }
  return <AppShell current="/research">
    <section className="page-intro compact"><p className="eyebrow">RESEARCH</p><h1>Know what the score can and cannot say.</h1><p className="lede">Quantrade turns dated quantitative evidence into a readable starting point for research.</p></section>
    <section className="content-section methodology"><div><p className="eyebrow">MODEL</p><h2>{card?.modelVersion ?? "Baseline research model"}</h2></div><div><p>{card?.purpose ?? "A transparent equal-weight reference that ranks only eligible research inputs."}</p><dl><div><dt>Status</dt><dd>{card?.status?.replaceAll("_", " ") ?? "Research-only"}</dd></div><div><dt>Data capability</dt><dd>Tier {card?.dataCapabilityTier ?? "B"}</dd></div><div><dt>Protocol</dt><dd>{card?.protocolVersion ?? "0.1"}</dd></div></dl></div></section>
    <section className="content-section methodology"><div><p className="eyebrow">METHOD</p><h2>How a score is formed</h2></div><div><p>{card?.methodology ?? "Sector-aware feature percentiles are averaged only when every required input is available."}</p><Link href="/rankings" className="text-link">Open dated rankings</Link></div></section>
    <section className="content-section methodology" id="track-record"><div><p className="eyebrow">TRACK RECORD</p><h2>Paper portfolio</h2></div><div>{portfolio ? <><p>A dated research basket, scored {formatResearchDate(portfolio.scoreDate)} and executed at the following regular-session open on {formatResearchDate(portfolio.executionDate)}.</p><dl><div><dt>Starting NAV</dt><dd>${Number(portfolio.startingNav).toLocaleString("en-CA")}</dd></div><div><dt>Positions</dt><dd>{portfolio.positions.length}</dd></div></dl></> : <p>No paper portfolio is published yet. This record appears only after an eligible score run can be executed under the documented next-session rule.</p>}</div></section>
    <section className="content-section methodology"><div><p className="eyebrow">LIMITS</p><h2>Read uncertainty plainly.</h2></div><div><ul className="plain-list">{card?.limitations?.map((limitation) => <li key={limitation}>{limitation}</li>) ?? <><li>Tier B data does not verify historical constituent or delisting coverage.</li><li>A research score is not investment advice, a prediction, or a guarantee.</li><li>Unavailable data blocks publication instead of being substituted.</li></>}</ul>{unavailable && <p className="inline-notice">The stored model card is unavailable until the research database is connected.</p>}</div></section>
  </AppShell>;
}
