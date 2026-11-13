"use client";

import { useId, useState } from "react";
import type { ReaderPassage } from "@/lib/api";
import { renderVerseMarkers } from "@/lib/verse-markers";
import { rejectedLabel } from "@/lib/passageRole";
import { RejectedVoice } from "@/components/common/RejectedVoice";
import { TextLabels, hasTextLabels } from "@/components/common/PassageFacts";
import { passageTextLabels } from "@/lib/search-stream";

export function Passage({ passage, highlighted, history = [], highlightAnchor = null }: {
  passage: ReaderPassage;
  highlighted: boolean;
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
  return (
    <>
      {passage.passage_author && (
        <p className="mb-1 text-xs font-medium text-brand-muted">{passage.passage_author}</p>
      )}
      <RejectedVoice label={rejected}>
        <p
          id={`anchor-${passage.anchor}`}
          className="text-[length:var(--reader-font-size)] leading-[var(--reader-line-height)] text-brand-primary mb-3"
          style={{
            fontFamily: "Georgia, serif",
            ...(highlighted ? { background: "rgba(196,151,42,0.16)", borderRadius: 4, padding: "2px 4px" } : {}),
          }}
        >
          {passage.unit_label && !rejected && (
            <sup className="text-brand-muted mr-1" style={{ fontSize: 10 }}>{passage.unit_label}</sup>
          )}
          {renderVerseMarkers(passage.content)}
        </p>
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
          <p id={`anchor-${passage.anchor}`} className="text-sm leading-relaxed text-brand-muted" style={{ fontFamily: "Georgia, serif" }}>
            {renderVerseMarkers(passage.content)}
          </p>
        </div>
      )}
    </div>
  );
}
