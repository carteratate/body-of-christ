"use client";

import { type CSSProperties, useEffect, useLayoutEffect, useRef, useState } from "react";

import { getCollectionMeta } from "@/lib/collections";
import styles from "./QuotaControl.module.css";

const QUOTA_OPTIONS = [3, 4, 5] as const;
const LIGHT_NUMERAL_COLLECTIONS = new Set(["apostolic-exhortations"]);

interface QuotaControlProps {
  value: number;
  onChange: (quota: number) => void;
  focusedCollection: string | null;
}

export function QuotaControl({ value, onChange, focusedCollection }: QuotaControlProps) {
  const collection = focusedCollection ? getCollectionMeta(focusedCollection) : undefined;
  const focusedEligible = collection !== undefined;
  const previousEligibility = useRef(focusedEligible);
  const standardButtonRefs = useRef(new Map<number, HTMLButtonElement>());
  const tenButtonRef = useRef<HTMLButtonElement>(null);
  const bloomTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [showBloom, setShowBloom] = useState(false);

  useEffect(() => () => {
    if (bloomTimeoutRef.current) clearTimeout(bloomTimeoutRef.current);
  }, []);

  useLayoutEffect(() => {
    if (previousEligibility.current && !focusedEligible && document.activeElement === tenButtonRef.current) {
      const fallback = QUOTA_OPTIONS.includes(value as (typeof QUOTA_OPTIONS)[number]) ? value : 5;
      standardButtonRefs.current.get(fallback)?.focus();
    }
    if (!focusedEligible && showBloom) {
      if (bloomTimeoutRef.current) clearTimeout(bloomTimeoutRef.current);
      bloomTimeoutRef.current = null;
      queueMicrotask(() => setShowBloom(false));
    }
    previousEligibility.current = focusedEligible;
  }, [focusedEligible, showBloom, value]);

  const focusedStyle = collection
    ? ({ "--focused-quota-color": collection.color } as CSSProperties)
    : undefined;

  return (
    <div className="flex shrink-0 items-center gap-2">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Per source:
      </span>
      <div className={styles.viewport} role="group" aria-label="Results per source">
        <div
          className={`${styles.standardChoices} ${focusedEligible ? styles.standardChoicesShifted : ""}`}
        >
          {QUOTA_OPTIONS.map((q, i) => (
            <button
              key={q}
              ref={(element) => {
                if (element) standardButtonRefs.current.set(q, element);
                else standardButtonRefs.current.delete(q);
              }}
              type="button"
              onClick={() => {
                if (bloomTimeoutRef.current) clearTimeout(bloomTimeoutRef.current);
                bloomTimeoutRef.current = null;
                setShowBloom(false);
                onChange(q);
              }}
              aria-pressed={value === q}
              aria-label={`${q} passages per source`}
              className={[
                styles.standardButton,
                "border-y border-brand-surface text-xs transition-[color,background-color,border-radius] focus-visible:relative focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-focus",
                i === 0 ? "rounded-l-md border-l" : "border-l",
                i < QUOTA_OPTIONS.length - 1 ? "border-r border-brand-surface" : "",
                i === QUOTA_OPTIONS.length - 1 && !focusedEligible ? "rounded-r-md border-r" : "",
                value === q
                  ? "bg-brand-accent font-semibold text-brand-bg"
                  : "bg-brand-surface text-brand-muted hover:text-brand-primary",
              ].join(" ")}
            >
              {q}
            </button>
          ))}
        </div>
        <button
          ref={tenButtonRef}
          type="button"
          onClick={() => {
            if (value !== 10) {
              setShowBloom(true);
              if (bloomTimeoutRef.current) clearTimeout(bloomTimeoutRef.current);
              bloomTimeoutRef.current = setTimeout(() => setShowBloom(false), 750);
              onChange(10);
            }
          }}
          aria-label="10 passages per source"
          aria-pressed={focusedEligible && value === 10}
          aria-hidden={!focusedEligible}
          tabIndex={focusedEligible ? 0 : -1}
          data-selected={focusedEligible && value === 10}
          style={focusedStyle}
          className={[
            styles.tenButton,
            focusedEligible ? styles.tenButtonVisible : "",
            focusedEligible && value === 10 ? styles.tenButtonSelected : "",
            focusedEligible && value === 10
              ? collection && LIGHT_NUMERAL_COLLECTIONS.has(collection.key)
                ? "text-brand-contrast-light"
                : "text-brand-contrast-dark"
              : "text-brand-primary",
            "border-[4px] text-xs font-semibold focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-focus",
          ].join(" ")}
        >
          <span className={collection?.key === "papal-documents" && value === 10 ? styles.papalNumeral : undefined}>
            10
          </span>
          {showBloom && focusedEligible ? (
            <span
              aria-hidden="true"
              data-focused-quota-bloom=""
              className={styles.softBloom}
              onAnimationEnd={() => {
                if (bloomTimeoutRef.current) clearTimeout(bloomTimeoutRef.current);
                bloomTimeoutRef.current = null;
                setShowBloom(false);
              }}
            />
          ) : null}
        </button>
      </div>
    </div>
  );
}
