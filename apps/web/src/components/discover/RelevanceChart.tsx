"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { getCollectionMeta } from "@/lib/collections";
import type { CollectionScore } from "@/lib/api";

interface RelevanceChartProps {
  scores: CollectionScore[];
}

export function RelevanceChart({ scores }: RelevanceChartProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  function toggle(key: string) {
    setExpanded((prev) => (prev === key ? null : key));
  }

  return (
    <div className="space-y-2">
      {scores.map((s, i) => {
        const meta = getCollectionMeta(s.collection);
        const label = meta?.label ?? s.collection;
        const color = meta?.hex ?? "#C4972A";
        const isOpen = expanded === s.collection;

        return (
          <div key={s.collection}>
            <button
              onClick={() => toggle(s.collection)}
              className="w-full text-left group"
            >
              <div className="flex items-center gap-3">
                <span className="text-xs text-brand-muted w-32 shrink-0 truncate">
                  {label}
                </span>
                <div className="flex-1 h-7 bg-brand-bg rounded overflow-hidden relative">
                  <div
                    className="h-full rounded transition-all duration-700 ease-out"
                    style={{
                      width: `${Math.max(2, s.score * 100)}%`,
                      backgroundColor: color,
                      opacity: 0.85,
                      transitionDelay: `${i * 80}ms`,
                    }}
                  />
                </div>
                <span className="text-xs text-brand-muted w-10 text-right tabular-nums">
                  {s.score.toFixed(2)}
                </span>
                {isOpen ? (
                  <ChevronUp size={14} className="text-brand-muted shrink-0" />
                ) : (
                  <ChevronDown size={14} className="text-brand-muted shrink-0" />
                )}
              </div>
            </button>
            {isOpen && (
              <div className="ml-[calc(8rem+0.75rem)] mr-14 mt-1 mb-2 text-xs text-brand-muted leading-relaxed">
                {s.explanation}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
