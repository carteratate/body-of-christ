"use client";

import { COLLECTIONS } from "@/lib/collections";

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
        return (
          <button
            key={col.key}
            onClick={() => onToggleVisible(col.key)}
            aria-pressed={isVisible}
            className={[
              "rounded-full px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent",
              isVisible
                ? "bg-brand-accent text-brand-bg"
                : "border border-brand-surface bg-brand-surface text-brand-muted hover:text-brand-primary",
            ].join(" ")}
          >
            {col.label}
          </button>
        );
      })}
    </div>
  );
}
