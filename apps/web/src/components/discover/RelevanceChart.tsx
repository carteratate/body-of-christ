"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { getCollectionMeta } from "@/lib/collections";
import type { CollectionScore } from "@/lib/api";

interface RelevanceChartProps {
  scores: CollectionScore[];
  explanations: Record<string, string>;
  explanationsDone: boolean;
}

export function RelevanceChart({ scores, explanations, explanationsDone }: RelevanceChartProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [animated, setAnimated] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setAnimated(true), 50);
    return () => clearTimeout(t);
  }, [scores]);

  function toggle(key: string) {
    setExpanded((prev) => (prev === key ? null : key));
  }

  const maxScore = Math.max(...scores.map((s) => s.score), 0.01);

  return (
    <div className="space-y-3">
      {scores.map((s, i) => {
        const meta = getCollectionMeta(s.collection);
        const label = meta?.label ?? s.collection;
        const color = meta?.hex ?? "#C4972A";
        const isOpen = expanded === s.collection;
        const barWidth = animated ? (s.score / maxScore) * 100 : 0;
        const explanation = explanations[s.collection];
        const isExplaining = isOpen && !explanation && !explanationsDone;

        return (
          <div key={s.collection}>
            <button
              onClick={() => toggle(s.collection)}
              className="w-full text-left"
            >
              <div className="flex items-center gap-3 mb-1">
                <span className="text-sm text-brand-primary w-44 shrink-0 truncate font-medium">
                  {label}
                </span>
                <span className="text-xs text-brand-muted w-10 text-right tabular-nums shrink-0">
                  {s.score.toFixed(2)}
                </span>
                {isOpen ? (
                  <ChevronUp size={14} className="text-brand-muted shrink-0" />
                ) : (
                  <ChevronDown size={14} className="text-brand-muted shrink-0" />
                )}
              </div>
              <div className="flex items-center gap-3">
                <div className="w-44 shrink-0" />
                <div className="flex-1 h-6 bg-brand-bg rounded-md overflow-hidden">
                  <div
                    className="h-full rounded-md"
                    style={{
                      width: `${Math.max(1, barWidth)}%`,
                      backgroundColor: color,
                      transition: `width 800ms cubic-bezier(0.4, 0, 0.2, 1) ${i * 100}ms`,
                    }}
                  />
                </div>
              </div>
            </button>
            {isOpen && (
              <p className="ml-[calc(11rem+0.75rem)] mt-1.5 mb-1 text-xs text-brand-muted leading-relaxed pr-8">
                {explanation ?? (
                  isExplaining ? (
                    <span className="animate-pulse">Loading explanation...</span>
                  ) : (
                    <span className="opacity-40">No explanation available.</span>
                  )
                )}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
