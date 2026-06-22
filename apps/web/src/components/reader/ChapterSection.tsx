"use client";

import type { ReaderChapter } from "@/lib/api";
import { Passage } from "./Passage";

export function ChapterSection({
  chapter,
  highlightAnchor,
}: {
  chapter: ReaderChapter;
  highlightAnchor: string | null;
}) {
  return (
    <section data-chapter-key={chapter.chapter_key} className="max-w-[640px] mx-auto px-6 py-6">
      <h2
        className="text-xl font-semibold text-brand-primary mb-4"
        style={{ fontFamily: "Georgia, serif" }}
      >
        {chapter.chapter_label}
      </h2>
      {chapter.passages.map((p) => (
        <Passage key={p.id} passage={p} highlighted={p.anchor === highlightAnchor} />
      ))}
    </section>
  );
}
