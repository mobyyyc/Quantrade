"use client";

import { useState, type KeyboardEvent, type PointerEvent } from "react";
import type { DailyPricePoint } from "@/lib/research-read-model";

type PriceChartProps = {
  points: DailyPricePoint[];
  ticker: string;
};

function formatPrice(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function PriceChart({ points, ticker }: PriceChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  if (points.length < 2) {
    return <p className="empty-inline">Price history is not available for this company yet.</p>;
  }

  const prices = points.map((point) => Number(point.closePrice));
  const first = prices[0];
  const last = prices.at(-1) ?? first;
  const minimum = Math.min(...prices);
  const maximum = Math.max(...prices);
  const range = maximum - minimum || Math.max(maximum * 0.04, 1);
  const width = 640;
  const height = 220;
  const inset = 4;
  const coordinates = prices.map((price, index) => {
    const x = inset + (index / (prices.length - 1)) * (width - inset * 2);
    const y = inset + (1 - (price - minimum) / range) * (height - inset * 2);
    return { x, y };
  });
  const path = coordinates.map(({ x, y }) => `${x},${y}`).join(" ");
  const lastPoint = coordinates.at(-1);
  const firstPoint = coordinates[0];
  const change = ((last - first) / first) * 100;
  const direction = change >= 0 ? "positive-change" : "negative-change";
  const directionColor = change >= 0 ? "#22c55e" : "#ef4444";
  const gradientId = `price-gradient-${ticker.replaceAll(/[^a-z0-9]/gi, "-").toLowerCase()}`;
  const areaPath = `M ${coordinates.map(({ x, y }) => `${x} ${y}`).join(" L ")} L ${lastPoint?.x} ${height - inset} L ${firstPoint.x} ${height - inset} Z`;
  const start = new Date(`${points[0].sessionDate}T00:00:00Z`).toLocaleDateString("en-CA", { month: "short", day: "numeric", timeZone: "UTC" });
  const end = new Date(`${points.at(-1)?.sessionDate}T00:00:00Z`).toLocaleDateString("en-CA", { month: "short", day: "numeric", timeZone: "UTC" });
  const activePoint = activeIndex === null ? null : coordinates[activeIndex];
  const activePrice = activeIndex === null ? null : prices[activeIndex];
  const activeDate = activeIndex === null ? null : new Date(`${points[activeIndex].sessionDate}T00:00:00Z`).toLocaleDateString("en-CA", { month: "short", day: "numeric", timeZone: "UTC" });

  function setNearestPoint(event: PointerEvent<SVGSVGElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * width;
    const nextIndex = Math.round(((x - inset) / (width - inset * 2)) * (points.length - 1));
    setActiveIndex(Math.max(0, Math.min(points.length - 1, nextIndex)));
  }

  function moveWithKeyboard(event: KeyboardEvent<SVGSVGElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const current = activeIndex ?? points.length - 1;
    setActiveIndex(Math.max(0, Math.min(points.length - 1, current + (event.key === "ArrowLeft" ? -1 : 1))));
  }

  return <section className="price-panel" aria-labelledby="price-context-title">
    <div className="price-panel-heading">
      <div><p className="eyebrow">PRICE CONTEXT</p><h2 id="price-context-title">Recent price history</h2></div>
      <div className="price-change"><strong>{formatPrice(last)}</strong><span className={direction}>{change >= 0 ? "+" : ""}{change.toFixed(2)}% over this period</span></div>
    </div>
    <div className="price-chart-canvas">
      <svg className={`price-chart ${direction}`} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${ticker} moved from ${formatPrice(first)} to ${formatPrice(last)} between ${start} and ${end}, a ${change >= 0 ? "gain" : "loss"} of ${Math.abs(change).toFixed(2)} percent. Hover or use the arrow keys to inspect a session.`} preserveAspectRatio="none" tabIndex={0} onPointerMove={setNearestPoint} onPointerLeave={() => setActiveIndex(null)} onFocus={() => setActiveIndex(points.length - 1)} onBlur={() => setActiveIndex(null)} onKeyDown={moveWithKeyboard}>
        <defs>
          <linearGradient id={gradientId} gradientUnits="userSpaceOnUse" x1="0" x2="0" y1={inset} y2={height - inset}>
            <stop offset="0%" stopColor={directionColor} stopOpacity="0.24" />
            <stop offset="100%" stopColor={directionColor} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#${gradientId})`} />
        <polyline points={path} fill="none" vectorEffect="non-scaling-stroke" />
        {activePoint && <><line className="price-chart-guide" x1={activePoint.x} x2={activePoint.x} y1={inset} y2={height - inset} vectorEffect="non-scaling-stroke" /><circle className="price-chart-active-point" cx={activePoint.x} cy={activePoint.y} r="4.5" vectorEffect="non-scaling-stroke" /></>}
        <circle cx={lastPoint?.x} cy={lastPoint?.y} r="3.5" vectorEffect="non-scaling-stroke" />
      </svg>
      {activePoint && activePrice !== null && activeDate && <output className="price-chart-tooltip" style={{ left: `${(activePoint.x / width) * 100}%`, top: `${(activePoint.y / height) * 100}%` }}><strong>{formatPrice(activePrice)}</strong><span>{activeDate}</span></output>}
    </div>
    <div className="price-chart-range"><span>{start}</span><span>{end}</span></div>
  </section>;
}
