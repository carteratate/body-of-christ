"use client";

import { useRef, useState, type CSSProperties } from "react";
import { scopeOptions } from "@/lib/collection-scopes";
import { COLLECTIONS, hexToRgb } from "@/lib/collections";
import type { ScopeExclusions, SearchDraftEvent } from "@/lib/search-draft";
import { GenreFilter } from "./GenreFilter";
import styles from "./CollectionToggles.module.css";

type ScopeEvent = Extract<SearchDraftEvent, { readonly collection: string }>;

interface CollectionTogglesProps {
  activeCollections: readonly string[];
  onToggle: (collection: string) => void;
  /** Genre and issuer filters (5.1a); a collection without options has no caret. */
  excluded?: Readonly<Record<string, ScopeExclusions>>;
  onScopeEvent?: (event: ScopeEvent) => void;
  /** While a search runs its request is frozen: the carets stay but do nothing. */
  scopesLocked?: boolean;
}

function Caret() {
  return (
    <svg className={styles.caret} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M6 15l6-6 6 6" />
    </svg>
  );
}

export function CollectionToggles({
  activeCollections,
  onToggle,
  excluded = {},
  onScopeEvent,
  scopesLocked = false,
}: CollectionTogglesProps) {
  const [scopeOpen, setScopeOpen] = useState<string | null>(null);
  const openCue = useRef<HTMLButtonElement | null>(null);
  // A search starting closes the panel for good, not just while it runs.
  if (scopesLocked && scopeOpen !== null) setScopeOpen(null);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Sources:
      </span>

      {COLLECTIONS.map((col) => {
        const isActive = activeCollections.includes(col.key);
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

        if (onScopeEvent && scopeOptions(col.key)) {
          // The pill keeps its width: selecting slides the name left and shows the caret.
          const open = isActive && scopeOpen === col.key;
          return (
            <div
              key={col.key}
              className={styles.scoped}
              data-active={isActive}
              style={{
                ...(isActive ? activeStyle : inactiveStyle),
                "--rgb": rgb,
                "--c": col.color,
              } as CSSProperties}
            >
              <button
                type="button"
                className={styles.name}
                onClick={() => {
                  if (isActive && scopeOpen === col.key) setScopeOpen(null);
                  onToggle(col.key);
                }}
                aria-pressed={isActive}
              >
                {col.label}
              </button>
              <button
                type="button"
                className={styles.cue}
                onClick={(event) => {
                  openCue.current = event.currentTarget;
                  setScopeOpen(open ? null : col.key);
                }}
                aria-haspopup="dialog"
                aria-expanded={open}
                aria-label={`Filter ${col.label} by kind and pope`}
                aria-hidden={!isActive}
                disabled={scopesLocked}
                tabIndex={isActive ? 0 : -1}
              >
                <Caret />
              </button>
              {open && (
                <GenreFilter
                  collection={col}
                  anchor={openCue}
                  excluded={excluded[col.key]}
                  onEvent={onScopeEvent}
                  onClose={() => setScopeOpen(null)}
                />
              )}
            </div>
          );
        }

        // The Bible is a plain pill: its one-choice translation dropdown was removed.
        // A second translation should come back as a single-choice "Translation" list
        // in the 5.1a caret panel (GenreFilter, with a Bible entry in collection-scopes),
        // not as a dropdown on the pill.
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
