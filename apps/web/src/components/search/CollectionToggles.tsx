"use client";

import { useState } from "react";
import { COLLECTIONS, hexToRgb } from "@/lib/collections";
import { TranslationSelector } from "./TranslationSelector";

interface CollectionTogglesProps {
  activeCollections: string[];
  onToggle: (collection: string) => void;
  translation: string;
  onTranslationChange: (t: string) => void;
}

export function CollectionToggles({
  activeCollections,
  onToggle,
  translation,
  onTranslationChange,
}: CollectionTogglesProps) {
  const [translationOpen, setTranslationOpen] = useState(false);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Sources:
      </span>

      {COLLECTIONS.map((col) => {
        const isActive = activeCollections.includes(col.key);
        const isBible = col.key === "bible";
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

        if (isBible) {
          return (
            <div key={col.key} className="relative">
              {/* Split-button pill: left part toggles collection, right part opens translation dropdown */}
              <div
                className="flex items-center rounded-full text-xs font-medium transition-colors"
                style={isActive ? activeStyle : inactiveStyle}
              >
                <button
                  onClick={() => onToggle(col.key)}
                  className="flex items-center gap-1 py-1 pl-3 pr-1.5"
                  aria-pressed={isActive}
                >
                  {col.label}
                </button>
                <button
                  onClick={() => setTranslationOpen(true)}
                  aria-label="Select Bible translation"
                  aria-expanded={translationOpen}
                  className="py-1 pr-2 text-[9px] transition-opacity hover:opacity-70"
                >
                  ▾
                </button>
              </div>

              {translationOpen && (
                <TranslationSelector
                  value={translation}
                  onChange={(t) => {
                    onTranslationChange(t);
                  }}
                  onClose={() => setTranslationOpen(false)}
                />
              )}
            </div>
          );
        }

        return (
          <button
            key={col.key}
            onClick={() => onToggle(col.key)}
            aria-pressed={isActive}
            className="rounded-full px-3 py-1 text-xs font-medium transition-colors"
            style={isActive ? activeStyle : inactiveStyle}
          >
            {col.label}
          </button>
        );
      })}
    </div>
  );
}
