"use client";

import { type CSSProperties, useEffect, useLayoutEffect, useRef, useState } from "react";

import { getCollectionMeta } from "@/lib/collections";
import styles from "./QuotaControl.module.css";

const QUOTA_OPTIONS = [3, 4, 5] as const;
// Church law's red takes a light numeral on dark and a dark one on light; every other
// collection colour reads with the dark numeral in both themes.
const THEME_SENSITIVE_COLLECTIONS = new Set(["church-law"]);

interface QuotaControlProps {
  value: number;
  onChange: (quota: number) => void;
  focusedCollection: string | null;
}

/**
 * On phones the box is only as wide as the buttons shown (3·4·5, widening as 10 slides
 * in), so a parent that centres it centres the buttons, and the "Per source:" label
 * hangs off its left side, out of the flow. On wider screens it is laid out as before.
 */
export function QuotaControl({ value, onChange, focusedCollection }: QuotaControlProps) {
  const collection = focusedCollection ? getCollectionMeta(focusedCollection) : undefined;
  const focusedEligible = collection !== undefined;
  const previousEligibility = useRef(focusedEligible);
  const standardButtonRefs = useRef(new Map<number, HTMLButtonElement>());
  const tenButtonRef = useRef<HTMLButtonElement>(null);
  const pulseTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [showPulse, setShowPulse] = useState(false);

  useEffect(() => () => {
    if (pulseTimeoutRef.current) clearTimeout(pulseTimeoutRef.current);
  }, []);

  useLayoutEffect(() => {
    if (previousEligibility.current && !focusedEligible && document.activeElement === tenButtonRef.current) {
      const fallback = QUOTA_OPTIONS.includes(value as (typeof QUOTA_OPTIONS)[number]) ? value : 5;
      standardButtonRefs.current.get(fallback)?.focus();
    }
    if (!focusedEligible && showPulse) {
      if (pulseTimeoutRef.current) clearTimeout(pulseTimeoutRef.current);
      pulseTimeoutRef.current = null;
      queueMicrotask(() => setShowPulse(false));
    }
    previousEligibility.current = focusedEligible;
  }, [focusedEligible, showPulse, value]);

  const focusedStyle = collection
    ? ({ "--focused-quota-color": collection.color } as CSSProperties)
    : undefined;

  return (
    <div className="relative flex shrink-0 items-center gap-2">
      {/* On phones the bar is the screen's width: the label may use what lies between
          the bar's 16px padding and the selector (half its width, plus the 8px gap),
          wrapping onto two lines on the narrowest screens rather than running off. */}
      <span
        className={`text-[10px] font-medium uppercase tracking-widest text-brand-muted max-md:absolute max-md:right-full max-md:top-1/2 max-md:mr-2 max-md:w-max max-md:-translate-y-1/2 max-md:text-right max-md:leading-tight ${
          focusedEligible ? "max-md:max-w-[calc(50vw-98px)]" : "max-md:max-w-[calc(50vw-79.5px)]"}`}
      >
        Per source:
      </span>
      <div
        className={`${styles.viewport} ${focusedEligible ? styles.viewportWide : ""}`}
        role="group"
        aria-label="Results per source"
      >
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
                if (pulseTimeoutRef.current) clearTimeout(pulseTimeoutRef.current);
                pulseTimeoutRef.current = null;
                setShowPulse(false);
                onChange(q);
              }}
              aria-pressed={value === q}
              aria-label={`${q} passages per source`}
              className={[
                styles.standardButton,
                "border-y text-xs transition-[color,background-color,border-color,border-radius] focus-visible:relative focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-focus",
                i === 0 ? "rounded-l-md border-l" : "border-l",
                i < QUOTA_OPTIONS.length - 1 ? "border-r" : "",
                i === QUOTA_OPTIONS.length - 1 && !focusedEligible ? "rounded-r-md border-r" : "",
                value === q
                  ? "border-brand-accent bg-brand-accent font-semibold text-brand-bg"
                  : "border-brand-surface bg-brand-surface text-brand-muted hover:text-brand-primary",
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
              setShowPulse(true);
              if (pulseTimeoutRef.current) clearTimeout(pulseTimeoutRef.current);
              pulseTimeoutRef.current = setTimeout(() => setShowPulse(false), 1000);
              onChange(10);
            }
          }}
          onAnimationEnd={(event) => {
            if (event.target !== event.currentTarget) return;
            if (pulseTimeoutRef.current) clearTimeout(pulseTimeoutRef.current);
            pulseTimeoutRef.current = null;
            setShowPulse(false);
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
            showPulse && focusedEligible ? styles.attachedPulse : "",
            focusedEligible && value === 10
              ? collection && THEME_SENSITIVE_COLLECTIONS.has(collection.key)
                ? styles.themeSensitiveNumeral
                : "text-brand-contrast-dark"
              : "text-brand-primary",
            "border-[4px] text-xs font-semibold focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-focus",
          ].join(" ")}
        >
          <span>10</span>
        </button>
      </div>
    </div>
  );
}
