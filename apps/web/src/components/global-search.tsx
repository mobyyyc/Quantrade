"use client";

import { useEffect, useRef } from "react";

export function GlobalSearch() {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  return <form className="header-search" action="/search" role="search">
    <label className="sr-only" htmlFor="header-search-query">Search companies</label>
    <input
      ref={inputRef}
      id="header-search-query"
      name="query"
      type="search"
      placeholder="Search companies · Ctrl/⌘ K"
      aria-label="Search companies. Press Control or Command K to focus search."
      autoComplete="off"
      enterKeyHint="search"
    />
  </form>;
}
