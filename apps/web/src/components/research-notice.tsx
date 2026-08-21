import Link from "next/link";

export function ResearchNotice() {
  return (
    <aside className="research-notice" aria-labelledby="research-notice-title">
      <p className="eyebrow">RESEARCH CONTEXT</p>
      <h2 id="research-notice-title">Use this as a starting point, not an instruction.</h2>
      <p>
        Scores summarize dated quantitative research. Tier B data has limits,
        including unverified historical constituent and delisting coverage.
      </p>
      <Link href="/research" className="text-link">Read methodology and limits</Link>
    </aside>
  );
}
