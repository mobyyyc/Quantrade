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

export function formatUsdPrice(value: string | number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Number(value));
}

export function formatCompactUsd(value: string | number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Number(value));
}

export function formatPriceChange(closePrice: string, previousClosePrice?: string): { amount: string; percent: string; direction: "positive" | "negative" } | null {
  if (!previousClosePrice) return null;
  const close = Number(closePrice);
  const previous = Number(previousClosePrice);
  if (!Number.isFinite(close) || !Number.isFinite(previous) || previous === 0) return null;
  const change = close - previous;
  const percent = (change / previous) * 100;
  return {
    amount: `${change >= 0 ? "+" : "−"}${formatUsdPrice(Math.abs(change))}`,
    percent: `${change >= 0 ? "+" : "−"}${Math.abs(percent).toFixed(2)}%`,
    direction: change >= 0 ? "positive" : "negative",
  };
}
