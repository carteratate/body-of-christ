import { Fragment } from "react";
import { footnoteSegments, type Footnote } from "@/lib/footnotes";
import { renderVerseMarkers } from "@/lib/verse-markers";

/** A passage's text with a superscript marker, carrying the note's own number, at
 *  each footnote's offset (issue #279). Without notes it is the plain passage. */
export function PassageText({ content, footnotes }: { content: string; footnotes: Footnote[] }) {
  return (
    <p className="text-sm text-brand-primary leading-relaxed whitespace-pre-wrap">
      {footnotes.length === 0
        ? renderVerseMarkers(content)
        : footnoteSegments(content, footnotes).map((segment, i) =>
          segment.kind === "text"
            ? <Fragment key={i}>{renderVerseMarkers(segment.text)}</Fragment>
            : (
              <sup key={i} className="text-brand-accent" style={{ fontSize: 10 }}>
                {segment.n}
              </sup>
            ),
        )}
    </p>
  );
}

/** The passage's notes, listed under it in small type, numbered as in the source. */
export function PassageNotes({ footnotes }: { footnotes: Footnote[] }) {
  if (footnotes.length === 0) return null;
  return (
    <div className="mt-3" aria-label="Notes">
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-brand-muted">Notes</p>
      <ol className="mt-1 space-y-0.5">
        {footnotes.map((note, i) => (
          <li key={`${note.n}-${i}`} className="text-xs leading-snug text-brand-muted">
            {note.n}. {note.text}
          </li>
        ))}
      </ol>
    </div>
  );
}
