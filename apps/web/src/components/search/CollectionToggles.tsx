"use client";

import { useEffect, useRef, useState } from "react";
import { useAppContext } from "@/components/layout/AppShell";
import { updatePreferences } from "@/lib/api";
import { COLLECTIONS } from "@/lib/collections";
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
  const { token } = useAppContext();
  const [translationOpen, setTranslationOpen] = useState(false);
  const isMounted = useRef(false);

  // Debounced sync: when activeCollections changes, persist after 500ms.
  // Skip on mount to avoid a spurious API call on load.
  useEffect(() => {
    if (!isMounted.current) {
      isMounted.current = true;
      return;
    }
    if (!token) return;
    const timer = setTimeout(() => {
      updatePreferences(token, { default_collections: activeCollections }).catch(() => {});
    }, 500);
    return () => clearTimeout(timer);
  }, [activeCollections, token]);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Sources:
      </span>

      {COLLECTIONS.map((col) => {
        const isActive = activeCollections.includes(col.key);
        const isBible = col.key === "bible";

        if (isBible) {
          return (
            <div key={col.key} className="relative">
              {/* Split-button pill: left part toggles collection, right part opens translation dropdown */}
              <div
                className={[
                  "flex items-center rounded-full text-xs font-medium transition-colors",
                  isActive
                    ? "bg-brand-accent text-brand-bg"
                    : "border border-brand-surface bg-brand-surface text-brand-muted",
                ].join(" ")}
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
                    if (token) {
                      updatePreferences(token, { preferred_translation: t }).catch(() => {});
                    }
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
            className={[
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              isActive
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
