"use client";

import { Fragment } from "react";
import type { HeldText, ReaderChapter, ReaderPassage } from "@/lib/api";
import { certaintyTag, formatAttribution } from "@/lib/attribution";
import { SourceCredit } from "@/components/common/SourceLink";
import { heldAfter, heldBeforeFirst } from "@/lib/held-texts";
import { HeldLine } from "./HeldText";
import { Passage } from "./Passage";

/** The work these passages belong to, when its attribution differs from the
 *  document's (a Pseudo-Gregory work in a Gregory volume), as "Title · Pseudo-Gregory". */
function workLabel(chapter: ReaderChapter): { text: string; tag: string | null } | null {
  const works = chapter.document.works ?? [];
  const key = chapter.passages.find((p) => p.work_key)?.work_key;
  const work = key ? works.find((item) => item.work_key === key) : undefined;
  if (!work) return null;
  const tag = certaintyTag(work.certainty);
  const author = formatAttribution(work.author, { certainty: work.certainty }, null, { certainty: false });
  if (!tag && (!author || author === chapter.document.author)) return null;
  return { text: [work.title, author].filter(Boolean).join(" · "), tag };
}

export function ChapterSection({
  chapter,
  highlightAnchor,
  heldTexts = [],
  first = false,
}: {
  chapter: ReaderChapter;
  highlightAnchor: string | null;
  /** The document's held texts (4.3); each is shown after the passage it follows. */
  heldTexts?: HeldText[];
  /** The document's first chapter, where the held texts that open it are shown. */
  first?: boolean;
}) {
  // History passages (rule F) leave the reading flow and sit, collapsed, under the
  // passage that replaced them. One whose current passage is not in this chapter
  // stays where it is, so no text is lost.
  const ids = new Set(chapter.passages.map((p) => p.id));
  const history = new Map<string, ReaderPassage[]>();
  for (const p of chapter.passages) {
    if (p.superseded_by && ids.has(p.superseded_by)) {
      history.set(p.superseded_by, [...(history.get(p.superseded_by) ?? []), p]);
    }
  }
  const work = workLabel(chapter);
  const credit = chapter.document.facts?.source_credit?.trim() || null;
  return (
    <section data-chapter-key={chapter.chapter_key} className="max-w-[640px] mx-auto px-6 py-6">
      <h2
        className={`text-xl font-semibold text-brand-primary ${work ? "mb-1" : "mb-4"}`}
        style={{ fontFamily: "Georgia, serif" }}
      >
        {chapter.chapter_label}
      </h2>
      {work && (
        <p className="mb-4 text-xs text-brand-muted">
          {work.text}
          {work.tag && <span className="ml-1.5 rounded border border-brand-muted/40 px-1 text-[10px]">{work.tag}</span>}
        </p>
      )}
      {first && heldBeforeFirst(heldTexts).map((held) => <HeldLine key={held.key} held={held} />)}
      {chapter.passages.map((p) => (
        <Fragment key={p.id}>
          {p.superseded_by && ids.has(p.superseded_by)
            ? null
            : <Passage passage={p} highlighted={p.anchor === highlightAnchor} history={history.get(p.id)} highlightAnchor={highlightAnchor} />}
          {heldAfter(p.anchor, heldTexts).map((held) => <HeldLine key={held.key} held={held} />)}
        </Fragment>
      ))}
      {credit && <SourceCredit text={credit} />}
    </section>
  );
}
