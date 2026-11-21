// Held texts (corpus cleanup 4.3, issue #394): texts of a document that are not on
// TheoCorpus at present, listed in their place with a link to read them online. The
// API sends them with the table of contents, in reading order, each following the
// passage `after_anchor` (null for one that comes before every passage).

import type { HeldText, TocEntry } from "@/lib/api";

export type OverviewEntry =
  | { kind: "chapter"; entry: TocEntry; ordinal: number }
  | { kind: "held"; held: HeldText };

/**
 * The overview's entries in reading order: the held texts that come first, then each
 * chapter followed by the held texts after one of its passages. Ordinals count
 * chapters only. A held text whose chapter is not listed (the API drops such a list,
 * so only a stale cache could send one) goes last rather than disappear.
 */
export function placeHeldTexts(chapters: TocEntry[], held: HeldText[] = []): OverviewEntry[] {
  const byChapter = new Map<string, HeldText[]>();
  const listed = new Set(chapters.map((entry) => entry.chapter_key));
  const first: HeldText[] = [];
  const unplaced: HeldText[] = [];
  for (const text of held) {
    if (text.after_chapter_key === null) first.push(text);
    else if (listed.has(text.after_chapter_key)) {
      byChapter.set(text.after_chapter_key, [...(byChapter.get(text.after_chapter_key) ?? []), text]);
    } else unplaced.push(text);
  }
  const entries: OverviewEntry[] = first.map((text) => ({ kind: "held", held: text }));
  chapters.forEach((entry, index) => {
    entries.push({ kind: "chapter", entry, ordinal: index + 1 });
    // Shown once, after the first chapter entry with this key.
    for (const text of byChapter.get(entry.chapter_key) ?? []) entries.push({ kind: "held", held: text });
    byChapter.delete(entry.chapter_key);
  });
  return [...entries, ...unplaced.map((text): OverviewEntry => ({ kind: "held", held: text }))];
}

/** The held texts that come before the document's first passage. */
export function heldBeforeFirst(held: HeldText[] = []): HeldText[] {
  return held.filter((text) => text.after_anchor === null);
}

/** The held texts to show right after the passage `anchor`, in order. */
export function heldAfter(anchor: string, held: HeldText[] = []): HeldText[] {
  return held.filter((text) => text.after_anchor === anchor);
}

/** "1 text read online", "17 texts read online". */
export function heldCountLabel(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "text" : "texts"} read online`;
}
