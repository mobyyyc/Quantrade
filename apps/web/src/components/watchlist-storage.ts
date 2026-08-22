import type { SecuritySearchResult } from "@/lib/research-read-model";

export type WatchlistEntry = SecuritySearchResult;

const storageKey = "quantrade.watchlist.v1";

export function readWatchlist(): WatchlistEntry[] {
  try {
    const stored = JSON.parse(window.localStorage.getItem(storageKey) ?? "[]") as unknown;
    if (!Array.isArray(stored)) return [];
    return stored.filter((item): item is WatchlistEntry => Boolean(
      item && typeof item === "object" && "securityId" in item && "ticker" in item && "issuerName" in item,
    ));
  } catch {
    return [];
  }
}

export function writeWatchlist(entries: WatchlistEntry[]) {
  window.localStorage.setItem(storageKey, JSON.stringify(entries));
}
