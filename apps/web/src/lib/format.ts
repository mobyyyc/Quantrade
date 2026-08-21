export function formatResearchDate(value: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function formatScore(value: string): string {
  return Number(value).toFixed(0);
}

export function formatPercentile(value?: string): string {
  return value ? `${Math.round(Number(value) * 100)}th percentile` : "Unavailable";
}
