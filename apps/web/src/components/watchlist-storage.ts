import type { SecuritySearchResult } from "@/lib/research-read-model";

export type WatchlistEntry = SecuritySearchResult & {
  note?: string;
  tags?: string[];
};

const storageKey = "quantrade.watchlist.v2";
const legacyStorageKey = "quantrade.watchlist.v1";
const maximumNoteLength = 240;
const maximumTagLength = 24;
export const maximumWatchlistTags = 5;

function normalizeTags(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const tag = item.trim().replace(/\s+/g, " ").slice(0, maximumTagLength);
    const key = tag.toLocaleLowerCase();
    if (!tag || seen.has(key)) continue;
    seen.add(key);
    tags.push(tag);
    if (tags.length === maximumWatchlistTags) break;
  }
  return tags;
}

function normalizeEntry(value: unknown): WatchlistEntry | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (typeof item.securityId !== "string" || typeof item.ticker !== "string" || typeof item.issuerName !== "string") return null;
  const note = typeof item.note === "string" ? item.note.trim().slice(0, maximumNoteLength) : "";
  const tags = normalizeTags(item.tags);
  return {
    securityId: item.securityId,
    ticker: item.ticker,
    issuerName: item.issuerName,
    ...(note ? { note } : {}),
    ...(tags.length ? { tags } : {}),
  };
}

export function readWatchlist(): WatchlistEntry[] {
  try {
    const current = window.localStorage.getItem(storageKey);
    const stored = JSON.parse(current ?? window.localStorage.getItem(legacyStorageKey) ?? "[]") as unknown;
    if (!Array.isArray(stored)) return [];
    const seen = new Set<string>();
    const entries = stored.flatMap((item) => {
      const entry = normalizeEntry(item);
      if (!entry || seen.has(entry.securityId)) return [];
      seen.add(entry.securityId);
      return [entry];
    });
    if (!current && entries.length) writeWatchlist(entries);
    return entries;
  } catch {
    return [];
  }
}

export function writeWatchlist(entries: WatchlistEntry[]) {
  const normalized = entries.flatMap((entry) => {
    const value = normalizeEntry(entry);
    return value ? [value] : [];
  });
  window.localStorage.setItem(storageKey, JSON.stringify(normalized));
  window.localStorage.removeItem(legacyStorageKey);
}
