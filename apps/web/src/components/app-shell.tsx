import Link from "next/link";
import type { ReactNode } from "react";

const navigation = [
  { href: "/", label: "Today" },
  { href: "/rankings", label: "Rankings" },
  { href: "/search", label: "Search" },
  { href: "/research", label: "Research" },
];

export function AppShell({ children, current }: { children: ReactNode; current: string }) {
  return (
    <div className="app-frame">
      <header className="topbar">
        <Link href="/" className="brand" aria-label="Quantrade, Today">
          <span className="brand-mark">Q</span>
          <span>Quantrade</span>
        </Link>
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
        <Link href="/search" className="search-link">Search companies</Link>
      </header>
      <main className="app-main">{children}</main>
      <nav className="mobile-nav" aria-label="Primary navigation">
        {navigation.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={current === item.href ? "page" : undefined}
            className={current === item.href ? "mobile-nav-link mobile-nav-link-active" : "mobile-nav-link"}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
