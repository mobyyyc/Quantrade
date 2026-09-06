"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";

type NavigationItem = { href: string; label: string };

export function MobileSidebarNav({ navigation, current }: { navigation: NavigationItem[]; current: string }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const panelRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 701px)");
    const closeOnDesktop = () => { if (desktop.matches) setOpen(false); };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    if (!open) { panel.close(); return; }
    panel.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [open]);

  return <div className="mobile-sidebar-control">
    <button
      type="button"
      ref={triggerRef}
      className="mobile-menu-button"
      aria-label="Open navigation"
      aria-controls={panelId}
      aria-expanded={open}
      onClick={() => setOpen(true)}
    >
      <span aria-hidden="true">☰</span>
    </button>
      <dialog className="mobile-sidebar" id={panelId} ref={panelRef} aria-label="Primary navigation" onCancel={() => setOpen(false)} onClose={() => { setOpen(false); triggerRef.current?.focus(); }} onClick={(event) => { if (event.target === event.currentTarget && event.clientX > event.currentTarget.getBoundingClientRect().right) setOpen(false); }}>
        <div className="mobile-sidebar-header" onKeyDown={(event) => {
          if (event.key === "Tab" && event.shiftKey) {
            event.preventDefault();
            panelRef.current?.querySelector<HTMLAnchorElement>("nav a:last-child")?.focus();
          }
        }}>
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
            onKeyDown={(event) => {
              if (event.key === "Tab" && !event.shiftKey && item === navigation.at(-1)) {
                event.preventDefault();
                panelRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
              }
            }}
          >{item.label}</Link>)}
        </nav>
        <p className="mobile-sidebar-note">Private, dated equity research.</p>
      </dialog>
  </div>;
}
