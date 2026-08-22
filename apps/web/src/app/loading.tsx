export default function Loading() {
  return <main className="app-main loading-page" aria-busy="true" aria-label="Loading research">
    <div className="skeleton-line skeleton-kicker" />
    <div className="skeleton-line skeleton-title" />
    <div className="skeleton-line skeleton-copy" />
    <section className="skeleton-surface" aria-hidden="true">
      <div className="skeleton-line skeleton-section-title" />
      <div className="skeleton-row" />
      <div className="skeleton-row" />
      <div className="skeleton-row" />
    </section>
  </main>;
}
