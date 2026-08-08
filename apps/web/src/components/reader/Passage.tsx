"use client";

import type { ReaderPassage } from "@/lib/api";
import { renderVerseMarkers } from "@/lib/verse-markers";

export function Passage({ passage, highlighted }: { passage: ReaderPassage; highlighted: boolean }) {
  return (
    <p
      id={`anchor-${passage.anchor}`}
      className="text-[length:var(--reader-font-size)] leading-[var(--reader-line-height)] text-brand-primary mb-3"
      style={{
        fontFamily: "Georgia, serif",
        ...(highlighted ? { background: "rgba(196,151,42,0.16)", borderRadius: 4, padding: "2px 4px" } : {}),
      }}
    >
      {passage.unit_label && (
        <sup className="text-brand-muted mr-1" style={{ fontSize: 10 }}>{passage.unit_label}</sup>
      )}
      {renderVerseMarkers(passage.content)}
    </p>
  );
}
