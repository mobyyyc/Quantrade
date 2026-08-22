export function formatResearchDate(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return "Unavailable";
  }
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return "Unavailable";
  }
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function formatScore(value: string): string {
  return Number(value).toFixed(0);
}

export function formatPercentile(value?: string): string {
  return value ? `${Math.round(Number(value) * 100)}th percentile` : "Unavailable";
}
