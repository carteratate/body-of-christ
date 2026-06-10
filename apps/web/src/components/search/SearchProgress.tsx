"use client";

import { useState, useEffect, useLayoutEffect, useRef, useCallback } from "react";
import { getCollectionMeta } from "@/lib/collections";

type SearchPhase = "searching" | "ranking" | null;
type SegMode = "idle" | "filling" | "complete";

const PHASE_LABEL: Record<string, string> = {
  preparing: "Preparing…",
  searching: "Searching the tradition…",
  ranking:   "Refining the top matches…",
};

// blinking = line has reached this node but the SSE event hasn't confirmed it yet
// active   = SSE event arrived, node is solid yellow
function Dot({ active, blinking = false }: { active: boolean; blinking?: boolean }) {
  const isYellow = active || blinking;
  return (
    <div
      className={`w-4 h-4 rounded-full flex-shrink-0${blinking && !active ? " animate-pulse" : ""}`}
      style={{
        backgroundColor: isYellow ? "var(--color-brand-accent)" : "var(--color-brand-muted)",
        opacity: isYellow ? 1 : 0.3,
        transition: "background-color 0.5s, opacity 0.5s",
      }}
    />
  );
}

function Segment({ mode, duration, onFillComplete }: {
  mode: SegMode;
  duration: string;
  onFillComplete?: () => void;
}) {
  const fillRef = useRef<HTMLDivElement>(null);
  // Tracks whether the currently-running transition is the slow fill, so we
  // don't call onFillComplete for the quick 0.2s snap transition.
  const isFilling = useRef(false);

  useLayoutEffect(() => {
    const el = fillRef.current;
    if (!el) return;

    if (mode === "filling") {
      isFilling.current = true;
      el.style.transition = "none";
      el.style.transform = "scaleX(0)";
      void el.offsetWidth; // force reflow so transition starts from a clean 0
      el.style.transition = `transform ${duration} linear`;
      el.style.transform = "scaleX(1)";
    } else if (mode === "complete") {
      isFilling.current = false;
      // Capture mid-fill position, freeze there, then shoot to 100%.
      const cur = getComputedStyle(el).transform;
      el.style.transition = "none";
      if (cur && cur !== "none") el.style.transform = cur;
      void el.offsetWidth;
      el.style.transition = "transform 0.2s ease-out";
      el.style.transform = "scaleX(1)";
    } else {
      isFilling.current = false;
      el.style.transition = "none";
      el.style.transform = "scaleX(0)";
    }
  }, [mode, duration]);

  // Fire onFillComplete only when the slow fill transition ends naturally.
  useEffect(() => {
    const el = fillRef.current;
    if (!el) return;
    const handle = (e: TransitionEvent) => {
      if (e.propertyName === "transform" && isFilling.current) {
        onFillComplete?.();
      }
    };
    el.addEventListener("transitionend", handle);
    return () => el.removeEventListener("transitionend", handle);
  }, [onFillComplete]);

  return (
    <div className="relative w-28 h-0.5 mx-2 flex-shrink-0">
      <div className="absolute inset-0" style={{ backgroundColor: "var(--color-brand-muted)", opacity: 0.3 }} />
      <div
        ref={fillRef}
        className="absolute inset-0 origin-left"
        style={{ backgroundColor: "var(--color-brand-accent)", transform: "scaleX(0)" }}
      />
    </div>
  );
}

interface SearchProgressProps {
  phase: SearchPhase;
  collections: string[];
}

export function SearchProgress({ phase, collections }: SearchProgressProps) {
  const labelKey = phase ?? "preparing";
  const label = PHASE_LABEL[labelKey];

  const [seg1Mode, setSeg1Mode] = useState<SegMode>("idle");
  const [seg2Mode, setSeg2Mode] = useState<SegMode>("idle");
  // true when the fill animation reached the next node before the SSE event
  const [seg1Done, setSeg1Done] = useState(false);
  const [seg2Done, setSeg2Done] = useState(false);

  useEffect(() => {
    if (phase === "searching") {
      setSeg1Mode("filling");
      setSeg1Done(false);
      setSeg2Mode("idle");
      setSeg2Done(false);
    } else if (phase === "ranking") {
      setSeg1Mode("complete");
      setSeg1Done(false);
      setSeg2Mode("filling");
      setSeg2Done(false);
    } else {
      setSeg1Mode("idle");
      setSeg1Done(false);
      setSeg2Mode("idle");
      setSeg2Done(false);
    }
  }, [phase]);

  const onSeg1Complete = useCallback(() => setSeg1Done(true), []);
  const onSeg2Complete = useCallback(() => setSeg2Done(true), []);

  // Dot states
  const dot1Blinking = phase === null;                      // waiting for "searching"
  const dot1Active   = phase !== null;
  const dot2Blinking = seg1Mode === "filling" && seg1Done;  // line reached node2, waiting for "ranking"
  const dot2Active   = phase === "ranking";
  const dot3Blinking = seg2Mode === "filling" && seg2Done;  // line reached node3, waiting for done
  const dot3Active   = false;                               // component unmounts on done

  return (
    <div className="flex flex-col items-center justify-center py-20 gap-8">
      {/* Phase label — key triggers remount so animate-fade-in fires on each phase change */}
      <p key={labelKey} className="text-brand-primary text-3xl font-light animate-fade-in">
        {label}
      </p>

      {/* Collection badges */}
      <div className="flex flex-wrap gap-3 justify-center max-w-lg">
        {collections.map((col) => {
          const meta = getCollectionMeta(col);
          if (!meta) return null;
          return (
            <span
              key={col}
              style={{ borderColor: meta.color, color: meta.color }}
              className={`px-4 py-1.5 rounded-full text-sm border font-medium transition-opacity duration-500 ${
                phase === "searching" ? "animate-pulse" : "opacity-60"
              }`}
            >
              {meta.label}
            </span>
          );
        })}
      </div>

      {/* Corpus scale line */}
      <p className="text-brand-muted text-xs">
        Searching 30,325 passages across {collections.length}{" "}
        {collections.length === 1 ? "source" : "sources"}
      </p>

      {/* Segmented progress bar + labels */}
      <div className="flex flex-col items-center gap-3">
        <div className="flex items-center">
          <Dot active={dot1Active} blinking={dot1Blinking} />
          <Segment mode={seg1Mode} duration="10s" onFillComplete={onSeg1Complete} />
          <Dot active={dot2Active} blinking={dot2Blinking} />
          <Segment mode={seg2Mode} duration="5s" onFillComplete={onSeg2Complete} />
          <Dot active={dot3Active} blinking={dot3Blinking} />
        </div>
        <div className="grid grid-cols-3 w-72 text-sm">
          <span
            className="text-left transition-colors duration-300"
            style={{ color: dot1Active ? "var(--color-brand-accent)" : "var(--color-brand-muted)" }}
          >
            Searching
          </span>
          <span
            className="text-center transition-colors duration-300"
            style={{ color: dot2Active ? "var(--color-brand-accent)" : "var(--color-brand-muted)" }}
          >
            Ranking
          </span>
          <span className="text-right" style={{ color: "var(--color-brand-muted)", opacity: 0.4 }}>
            Results
          </span>
        </div>
      </div>
    </div>
  );
}
