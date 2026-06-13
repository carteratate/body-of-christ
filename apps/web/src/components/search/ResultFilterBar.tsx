"use client";

import { COLLECTIONS, hexToRgb } from "@/lib/collections";

interface ResultFilterBarProps {
  submittedCollections: string[];
  visibleCollections: string[];
  onToggleVisible: (c: string) => void;
}

export function ResultFilterBar({
  submittedCollections,
  visibleCollections,
  onToggleVisible,
}: ResultFilterBarProps) {
  const ordered = COLLECTIONS.filter((c) => submittedCollections.includes(c.key));

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Filter:
      </span>
      {ordered.map((col) => {
        const isVisible = visibleCollections.includes(col.key);
        const rgb = hexToRgb(col.hex);
        const activeStyle = {
          background: `rgba(${rgb},0.40)`,
          border: `1px solid rgba(${rgb},0.7)`,
          color: col.hex,
        };
        const inactiveStyle = {
          background: `rgba(${rgb},0.08)`,
          border: `1px solid rgba(${rgb},0.15)`,
          color: `rgba(${rgb},0.65)`,
        };
        return (
          <button
            key={col.key}
            onClick={() => onToggleVisible(col.key)}
            aria-pressed={isVisible}
            className="rounded-full px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            style={isVisible ? activeStyle : inactiveStyle}
          >
            {col.label}
          </button>
        );
      })}
    </div>
  );
}
