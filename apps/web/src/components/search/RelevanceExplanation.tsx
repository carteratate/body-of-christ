"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";

interface RelevanceExplanationProps {
  /** `null` while the explanation is still streaming; `""` when there is none. */
  explanation: string | null;
  chunkId: string;
  color: string;
  rgb: string;
}

/**
 * The AI explanation under an expanded result, closed until the reader asks for it.
 *
 * Closed, the header reads "Show why this is relevant (AI generated)". Without the verb,
 * a lone "(AI generated)" label under the passage reads as a caption for the passage —
 * which is the one thing on the card that is not AI generated. Opening drops "Show".
 *
 * Open/closed is local and unpersisted: the panel unmounts with the card body, so
 * re-expanding a card starts it closed again. Explanation deltas keep arriving through
 * `explanation` while it is closed, and an open panel fills in live.
 */
export function RelevanceExplanation({ explanation, chunkId, color, rgb }: RelevanceExplanationProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (explanation === "") return null;

  const bodyId = `chunk-explanation-${chunkId}`;
  const Chevron = isOpen ? ChevronUp : ChevronDown;

  return (
    <div
      style={{
        marginTop: "12px",
        borderRadius: "6px",
        background: `rgba(${rgb},0.06)`,
        border: `1px solid rgba(${rgb},0.15)`,
      }}
    >
      <button
        type="button"
        onClick={() => setIsOpen((value) => !value)}
        aria-expanded={isOpen}
        aria-controls={bodyId}
        className="flex min-h-9 w-full items-center gap-1.5 rounded-md px-3 py-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-accent"
      >
        <Sparkles size={11} style={{ color }} />
        <span style={{ fontSize: "10px", color, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em" }}>
          {isOpen ? "Why this is relevant (AI generated)" : "Show why this is relevant (AI generated)"}
        </span>
        <Chevron size={15} className="ml-auto shrink-0 text-brand-muted" />
      </button>
      {isOpen && (
        <div id={bodyId} className="px-3 pb-3">
          {explanation === null ? (
            <div data-testid="explanation-skeleton" className="animate-pulse space-y-2">
              <div className="h-3 rounded w-full" style={{ background: `rgba(${rgb},0.12)` }} />
              <div className="h-3 rounded w-5/6" style={{ background: `rgba(${rgb},0.12)` }} />
              <div className="h-3 rounded w-3/4" style={{ background: `rgba(${rgb},0.12)` }} />
            </div>
          ) : (
            <p className="text-sm text-brand-primary leading-relaxed">{explanation}</p>
          )}
        </div>
      )}
    </div>
  );
}
