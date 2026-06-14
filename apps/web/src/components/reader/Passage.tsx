"use client";

import type { ReaderPassage } from "@/lib/api";

export function Passage({ passage, highlighted }: { passage: ReaderPassage; highlighted: boolean }) {
  return (
    <p
      id={`anchor-${passage.anchor}`}
      className="text-[15px] leading-[1.9] text-brand-primary mb-3"
      style={{
        fontFamily: "Georgia, serif",
        ...(highlighted ? { background: "rgba(196,151,42,0.16)", borderRadius: 4, padding: "2px 4px" } : {}),
      }}
    >
      {passage.unit_label && (
        <sup className="text-brand-muted mr-1" style={{ fontSize: 10 }}>{passage.unit_label}</sup>
      )}
      {passage.content}
    </p>
  );
}
