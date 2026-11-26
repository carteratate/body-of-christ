"use client";

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Check, X } from "lucide-react";

import {
  SCOPED_COLLECTIONS, scopeOptions, visibleScopeValues, type ScopeFacet, type ScopeValue,
} from "@/lib/collection-scopes";
import { hexToRgb, type CollectionMeta } from "@/lib/collections";
import type { ScopeExclusions, SearchDraftEvent } from "@/lib/search-draft";
import styles from "./GenreFilter.module.css";

type ScopeEvent = Extract<SearchDraftEvent, { readonly collection: string }>;

interface GenreFilterProps {
  collection: CollectionMeta;
  /** The caret the panel grows out of. */
  anchor: RefObject<HTMLElement | null>;
  excluded: ScopeExclusions | undefined;
  onEvent: (event: ScopeEvent) => void;
  onClose: () => void;
}

const MARGIN = 8;
const GAP = 10;
const HEADER = 48;
const MIN_LIST = 160;

const HEADINGS: Record<ScopeFacet, { heading: string; plural: string }> = {
  genres: { heading: "Kind", plural: "kinds" },
  issuers: { heading: "Pope", plural: "popes" },
  documents: { heading: "Work", plural: "works" },
};

/**
 * What to search inside one collection, all ticked to start: its kinds and its popes
 * (5.1a), or its works (the work filter, Catechism for now). Opens out of the caret in the collection's pill, the same on phone and laptop,
 * and closes on any press outside it or on Escape.
 */
export function GenreFilter({ collection, anchor, excluded, onEvent, onClose }: GenreFilterProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{
    left: number; top?: number; bottom?: number; pointer: number; maxHeight: number;
  } | null>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useLayoutEffect(() => {
    function measure() {
      const panel = panelRef.current;
      const cue = anchor.current;
      if (!panel || !cue) return;
      const rect = cue.getBoundingClientRect();
      const width = panel.offsetWidth;
      const centre = rect.left + rect.width / 2;
      const left = Math.max(MARGIN, Math.min(window.innerWidth - width - MARGIN, centre - width / 2));
      // Above the caret, as a rule (the bar sits at the bottom); below it when a long
      // question has pushed the caret near the top. The list takes what room is left,
      // less the header.
      const above = rect.top - GAP - MARGIN;
      const below = window.innerHeight - rect.bottom - GAP - MARGIN;
      const placeBelow = above < MIN_LIST + HEADER && below > above;
      setPlace({
        left,
        pointer: centre - left,
        ...(placeBelow
          ? { top: rect.bottom + GAP, maxHeight: Math.max(0, below - HEADER) }
          : { bottom: window.innerHeight - rect.top + GAP, maxHeight: Math.max(0, above - HEADER) }),
      });
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [anchor]);

  // Focus moves into the panel when it opens, so Tab walks its lists; Escape and the
  // close button hand it back to the caret. A press elsewhere keeps its own target.
  // Only once it is placed and visible: a browser does not focus a hidden element.
  const placed = place !== null;
  useEffect(() => {
    if (!placed) return;
    panelRef.current?.querySelector<HTMLElement>('[role="checkbox"]')?.focus({ preventScroll: true });
  }, [placed]);

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || anchor.current?.contains(target)) return;
      onCloseRef.current();
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      onCloseRef.current();
      anchor.current?.focus();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [anchor]);

  const options = scopeOptions(collection.key);
  if (!options) return null;
  // Kind and Pope each show what the other's ticks leave, with those counts; a work
  // is one document, so the Work list has no count.
  const counted = visibleScopeValues(options, excluded);
  const shown: Record<ScopeFacet, (ScopeValue & { documents?: number })[]> = {
    ...counted, documents: [...options.documents],
  };
  const facets = SCOPED_COLLECTIONS[collection.key] ?? [];
  const sections = facets.filter((facet) => options[facet].length > (facet === "genres" ? 1 : 0));

  const style = {
    "--rgb": hexToRgb(collection.hex),
    "--c": collection.color,
    "--pointer": `${place?.pointer ?? 0}px`,
    left: place?.left ?? 0,
    top: place?.top,
    bottom: place?.top === undefined ? place?.bottom ?? 0 : undefined,
    visibility: place ? "visible" : "hidden",
  } as CSSProperties;

  function toggle(facet: ScopeFacet, value: string): ScopeEvent {
    if (facet === "genres") return { type: "genre-toggled", collection: collection.key, genre: value };
    if (facet === "issuers") return { type: "issuer-toggled", collection: collection.key, issuer: value };
    return { type: "document-toggled", collection: collection.key, document: value };
  }

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label={`Search within ${collection.label}`}
      className={styles.panel}
      data-below={place?.top !== undefined || undefined}
      style={style}
    >
      <div className={styles.head}>
        <span className={styles.dot} aria-hidden />
        Search within {collection.label}
        <button
          type="button"
          className={styles.close}
          onClick={() => {
            onClose();
            anchor.current?.focus();
          }}
          aria-label="Close"
        >
          <X size={14} />
        </button>
      </div>
      <div className={styles.scroll} style={{ maxHeight: place ? Math.min(place.maxHeight, 380) : undefined }}>
        {sections.map((facet) => {
          const { heading, plural } = HEADINGS[facet];
          const off = excluded?.[facet] ?? [];
          return (
            <div key={facet} role="group" aria-label={heading}>
              <div className={styles.section}>
                <span className={styles.heading}>{heading}</span>
                <button
                  type="button"
                  className={styles.pillButton}
                  disabled={off.length === 0}
                  onClick={() => onEvent({ type: "scope-all", collection: collection.key, facet })}
                  aria-label={`All ${plural}`}
                >
                  All
                </button>
              </div>
              {shown[facet].map((option) => {
                const ticked = !off.includes(option.value);
                // The last ticked value shown cannot be unticked, or the search would
                // find nothing in this collection.
                const onlyTicked = ticked
                  && shown[facet].filter((other) => !off.includes(other.value)).length === 1;
                return (
                  <div key={option.value} className={styles.row}>
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={ticked}
                      aria-disabled={onlyTicked || undefined}
                      title={onlyTicked ? "At least one stays ticked" : undefined}
                      className={styles.option}
                      onClick={() => {
                        if (!onlyTicked) onEvent(toggle(facet, option.value));
                      }}
                    >
                      <span className={styles.box} aria-hidden>
                        {ticked && <Check size={11} strokeWidth={3.5} />}
                      </span>
                      {option.detail ? (
                        <span className={styles.titled}>
                          <span className={styles.label}>{option.label}</span>
                          <span className={styles.detail}>{option.detail}</span>
                        </span>
                      ) : (
                        <span className={styles.label}>{option.label}</span>
                      )}
                      {option.documents !== undefined && (
                        <span className={styles.count} aria-label={`${option.documents} documents`}>
                          {option.documents}
                        </span>
                      )}
                    </button>
                    <button
                      type="button"
                      className={`${styles.pillButton} ${styles.only}`}
                      onClick={() => onEvent({
                        type: "scope-only", collection: collection.key, facet, value: option.value,
                      })}
                      aria-label={`Only ${option.label}`}
                    >
                      Only
                    </button>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>,
    document.body,
  );
}
