"use client";

import { useId, useState } from "react";
import type { ReaderPassage } from "@/lib/api";
import { renderVerseMarkers } from "@/lib/verse-markers";
import { parseHeadings } from "@/lib/passage-headings";
import { opensWithRole, rejectedLabel } from "@/lib/passageRole";
import { PassageBlocks } from "@/components/common/PassageBlocks";
import { RejectedVoice } from "@/components/common/RejectedVoice";
import { TextLabels, hasTextLabels } from "@/components/common/PassageFacts";
import { passageTextLabels } from "@/lib/search-stream";

export function Passage({ passage, highlighted, history = [], highlightAnchor = null, opensChapter = false }: {
  passage: ReaderPassage;
  highlighted: boolean;
  /** The passage opens its chapter, under the chapter heading: a level-1 heading that
   *  repeats that heading is not shown again (issue #445). */
  opensChapter?: boolean;
  /** Older wording this passage replaced (rule F, D11), shown collapsed under it. */
  history?: ReaderPassage[];
  /** Opens the older wording a link points at. */
  highlightAnchor?: string | null;
}) {
  // A position the document rejects (2.4d): set off as a quotation under a caption
  // naming whose it is, which replaces the inline marker.
  const rejected = rejectedLabel(passage);
  // Where the text came from (2.4f): a scanned edition, or unofficial canon English.
  const textLabels = passageTextLabels(passage);
  // Headings marked inside the passage (issue #445). Without them it is drawn as before.
  const headings = parseHeadings(passage.headings, passage.content);
  const textClass = "text-[length:var(--reader-font-size)] leading-[var(--reader-line-height)] whitespace-pre-wrap text-brand-primary mb-3";
  const textStyle = {
    fontFamily: "Georgia, serif",
    ...(highlighted ? { background: "rgba(196,151,42,0.16)", borderRadius: 4, padding: "2px 4px" } : {}),
  };
  // The unit marker (`§79`) marks the passage's first paragraph, not a heading above it.
  const unitMarker = (text: string) => (
    passage.unit_label && !rejected && !opensWithRole(text, passage.unit_label)
      ? <sup className="text-brand-muted mr-1" style={{ fontSize: 10 }}>{passage.unit_label}</sup>
      : null
  );
  return (
    <>
      {passage.passage_author && (
        <p className="mb-1 text-xs font-medium text-brand-muted">{passage.passage_author}</p>
      )}
      <RejectedVoice label={rejected}>
        {headings.length > 0
          ? (
            <PassageBlocks
              surface="reader"
              id={`anchor-${passage.anchor}`}
              content={passage.content}
              headings={headings}
              className={textClass}
              style={textStyle}
              hideChapterTitle={opensChapter}
              unitMarker={unitMarker}
            />
          )
          : (
            <p id={`anchor-${passage.anchor}`} className={textClass} style={textStyle}>
              {unitMarker(passage.content)}
              {renderVerseMarkers(passage.content)}
            </p>
          )}
      </RejectedVoice>
      {hasTextLabels(textLabels) && (
        <div className="-mt-1 mb-3 space-y-1 text-xs leading-snug text-brand-muted">
          <TextLabels labels={textLabels} />
        </div>
      )}
      {passage.note && <p className="-mt-1 mb-3 text-xs leading-snug text-brand-muted">{passage.note}</p>}
      {history.map((older) => <EarlierText key={older.id} passage={older} initiallyOpen={older.anchor === highlightAnchor} />)}
    </>
  );
}

/** The year a history passage's text took effect, from its anchor
 *  (`can/295/history-1983`), or null. */
export function historyYear(anchor: string): string | null {
  return anchor.match(/\/history-(\d{3,4})$/)?.[1] ?? null;
}

/** An older wording, collapsed under the passage that replaced it. */
function EarlierText({ passage, initiallyOpen }: { passage: ReaderPassage; initiallyOpen: boolean }) {
  const [open, setOpen] = useState(initiallyOpen);
  const bodyId = useId();
  const year = historyYear(passage.anchor);
  return (
    <div className="-mt-1 mb-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="text-xs text-brand-muted underline-offset-2 hover:text-brand-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
      >
        {open ? "▾" : "▸"} Earlier text{year ? ` (${year})` : ""}
      </button>
      {open && (
        <div id={bodyId} className="mt-1 border-l-2 border-brand-muted/30 pl-3">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-brand-muted">No longer in force</p>
          <p id={`anchor-${passage.anchor}`} className="text-sm leading-relaxed whitespace-pre-wrap text-brand-muted" style={{ fontFamily: "Georgia, serif" }}>
            {renderVerseMarkers(passage.content)}
          </p>
        </div>
      )}
    </div>
  );
}
