"use client";

import { useEffect, useState } from "react";
import type { SecuritySearchResult } from "@/lib/research-read-model";
import { loadWatchlist, writeWatchlist } from "@/components/watchlist-storage";

export function WatchlistButton({ company }: { company: SecuritySearchResult }) {
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    void loadWatchlist().then((entries) => {
      if (active) setSaved(entries.some((entry) => entry.securityId === company.securityId));
    });
    return () => { active = false; };
  }, [company.securityId]);

  const toggle = async () => {
    const entries = await loadWatchlist();
    const exists = entries.some((entry) => entry.securityId === company.securityId);
    await writeWatchlist(exists ? entries.filter((entry) => entry.securityId !== company.securityId) : [...entries, company]);
    setSaved(!exists);
  };

  return <button type="button" className="quiet-button detail-watchlist-button" onClick={() => void toggle()} aria-pressed={saved}>
    {saved ? "Saved" : "Save to watchlist"}
  </button>;
}
