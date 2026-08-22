"use client";

import { useEffect, useId, useState } from "react";
import Link from "next/link";

type NavigationItem = { href: string; label: string };

export function MobileSidebarNav({ navigation, current }: { navigation: NavigationItem[]; current: string }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  return <div className="mobile-sidebar-control">
    <button
      type="button"
      className="mobile-menu-button"
      aria-label="Open navigation"
      aria-controls={panelId}
      aria-expanded={open}
      onClick={() => setOpen(true)}
    >
      <span aria-hidden="true">☰</span>
    </button>
    {open && <>
      <button className="mobile-sidebar-backdrop" type="button" aria-label="Close navigation" onClick={() => setOpen(false)} />
      <aside className="mobile-sidebar" id={panelId} aria-label="Primary navigation">
        <div className="mobile-sidebar-header">
          <span className="brand-mark">Q</span>
          <strong>Quantrade</strong>
          <button type="button" className="mobile-menu-button" aria-label="Close navigation" onClick={() => setOpen(false)}>×</button>
        </div>
        <nav className="mobile-sidebar-links">
          {navigation.map((item) => <Link
            key={item.href}
            href={item.href}
            aria-current={current === item.href ? "page" : undefined}
            className={current === item.href ? "sidebar-link sidebar-link-active" : "sidebar-link"}
            onClick={() => setOpen(false)}
          >{item.label}</Link>)}
        </nav>
        <p className="mobile-sidebar-note">Private, dated equity research.</p>
      </aside>
    </>}
  </div>;
}
