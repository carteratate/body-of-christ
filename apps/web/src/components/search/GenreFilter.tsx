"use client";

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Check, X } from "lucide-react";

import { scopeOptions, type ScopeFacet } from "@/lib/collection-scopes";
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

/**
 * What to search inside one collection (5.1a): its kinds and its popes, all ticked to
 * start. Opens out of the caret in the collection's pill, the same on phone and laptop,
 * and closes on any press outside it or on Escape.
 */
export function GenreFilter({ collection, anchor, excluded, onEvent, onClose }: GenreFilterProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ left: number; bottom: number; pointer: number; maxHeight: number } | null>(null);
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
      setPlace({
        left,
        bottom: window.innerHeight - rect.top + GAP,
        pointer: centre - left,
        // The room above the caret, less the header; never taller than the screen allows.
        maxHeight: Math.max(0, rect.top - GAP - MARGIN - 48),
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

  const sections: { facet: ScopeFacet; heading: string }[] = [
    ...(options.genres.length > 1 ? [{ facet: "genres" as const, heading: "Kind" }] : []),
    ...(options.issuers.length > 0 ? [{ facet: "issuers" as const, heading: "Pope" }] : []),
  ];

  const style = {
    "--rgb": hexToRgb(collection.hex),
    "--c": collection.color,
    "--pointer": `${place?.pointer ?? 0}px`,
    left: place?.left ?? 0,
    bottom: place?.bottom ?? 0,
    visibility: place ? "visible" : "hidden",
  } as CSSProperties;

  function toggle(facet: ScopeFacet, value: string): ScopeEvent {
    return facet === "genres"
      ? { type: "genre-toggled", collection: collection.key, genre: value }
      : { type: "issuer-toggled", collection: collection.key, issuer: value };
  }

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label={`Search within ${collection.label}`}
      className={styles.panel}
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
        {sections.map(({ facet, heading }) => {
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
                  aria-label={`All ${heading === "Pope" ? "popes" : "kinds"}`}
                >
                  All
                </button>
              </div>
              {options[facet].map((option) => {
                const ticked = !off.includes(option.value);
                return (
                  <div key={option.value} className={styles.row}>
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={ticked}
                      className={styles.option}
                      onClick={() => onEvent(toggle(facet, option.value))}
                    >
                      <span className={styles.box} aria-hidden>
                        {ticked && <Check size={11} strokeWidth={3.5} />}
                      </span>
                      <span className={styles.label}>{option.label}</span>
                      <span className={styles.count} aria-label={`${option.documents} documents`}>
                        {option.documents}
                      </span>
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
