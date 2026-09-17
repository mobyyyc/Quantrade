import Link from "next/link";
import type { ReactNode } from "react";
import { GlobalSearch } from "@/components/global-search";
import { MobileSidebarNav } from "@/components/mobile-sidebar-nav";
import { AccountControl } from "@/components/account-control";
import { isDemoMode } from "@/lib/demo-mode";

const navigation = [
  { href: "/", label: "Today" },
  { href: "/rankings", label: "Rankings" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/research", label: "Research" },
];

export function AppShell({ children, current }: { children: ReactNode; current: string }) {
  const demoMode = isDemoMode();
  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <header className="topbar">
        <div className="topbar-brand">
          <MobileSidebarNav navigation={navigation} current={current} />
          <Link href="/" className="brand" aria-label="Quantrade, Today">
            <span className="brand-mark">Q</span>
            <span>Quantrade</span>
          </Link>
          {demoMode && <span className="demo-mode-label" title="Generated values, not live market data">Synthetic demo</span>}
        </div>
        <nav className="desktop-nav" aria-label="Primary navigation">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={current === item.href ? "page" : undefined}
              className={current === item.href ? "nav-link nav-link-active" : "nav-link"}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="topbar-actions"><GlobalSearch /><AccountControl /></div>
      </header>
      <main id="main-content" className="app-main" tabIndex={-1}>{children}</main>
    </div>
  );
}
