"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

export function ScrollFadeRegion({ children, className = "", ariaLabel }: { children: ReactNode; className?: string; ariaLabel: string }) {
  const regionRef = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ top: false, bottom: false });

  useEffect(() => {
    const region = regionRef.current;
    if (!region) return;
    const updateEdges = () => setEdges({
      top: region.scrollTop > 2,
      bottom: region.scrollTop + region.clientHeight < region.scrollHeight - 2,
    });
    updateEdges();
    region.addEventListener("scroll", updateEdges, { passive: true });
    const observer = new ResizeObserver(updateEdges);
    observer.observe(region);
    return () => {
      region.removeEventListener("scroll", updateEdges);
      observer.disconnect();
    };
  }, []);

  return <div className={`scroll-fade-frame ${className}${edges.top ? " has-top-fade" : ""}${edges.bottom ? " has-bottom-fade" : ""}`}><div ref={regionRef} className="scroll-fade-region" tabIndex={0} aria-label={ariaLabel}>{children}</div></div>;
}
