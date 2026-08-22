"use client";

import { useEffect, useState } from "react";
import type { SecuritySearchResult } from "@/lib/research-read-model";
import { readWatchlist, writeWatchlist } from "@/components/watchlist-storage";

export function WatchlistButton({ company }: { company: SecuritySearchResult }) {
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSaved(readWatchlist().some((entry) => entry.securityId === company.securityId));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [company.securityId]);

  const toggle = () => {
    const entries = readWatchlist();
    const exists = entries.some((entry) => entry.securityId === company.securityId);
    writeWatchlist(exists ? entries.filter((entry) => entry.securityId !== company.securityId) : [...entries, company]);
    setSaved(!exists);
  };

  return <button type="button" className="quiet-button detail-watchlist-button" onClick={toggle} aria-pressed={saved}>
    {saved ? "Saved" : "Save to watchlist"}
  </button>;
}
