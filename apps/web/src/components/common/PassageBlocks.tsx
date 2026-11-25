import { Fragment, type CSSProperties, type ReactNode } from "react";
import { footnoteSegments, type Footnote } from "@/lib/footnotes";
import {
  noteBlockIndex,
  passageBlocks,
  type HeadingLevel,
  type PassageBlock,
  type PassageHeading,
} from "@/lib/passage-headings";
import { renderVerseMarkers } from "@/lib/verse-markers";

/**
 * A passage whose headings are marked (issue #445), drawn as its headings, epigraphs and
 * paragraphs. Only passages with marks come here: an unmarked passage keeps the single
 * paragraph it has always had (`PassageText`, the reader's `Passage`).
 *
 * The styles are the passage-headings survey's specification
 * (docs/corpus-cleanup/passage-headings-survey.md): three levels and an epigraph, in the
 * passage's own face, with brand tokens only. Levels 1 and 2 are set in capitals by CSS
 * so sources that print one level in either case agree; level 3 keeps its printed case.
 * A heading's space above is larger than below, and stacked headings lose the space
 * above, so each reads with the text it introduces.
 */

type Surface = "card" | "reader";

const CARD_CLASS: Record<HeadingLevel, string> = {
  1: "text-[11px] font-semibold uppercase tracking-[0.08em] text-brand-muted",
  2: "text-[12.5px] font-semibold uppercase tracking-[0.05em] text-brand-primary",
  3: "text-sm font-semibold text-brand-primary",
};
const READER_CLASS: Record<HeadingLevel, string> = {
  1: "font-semibold uppercase tracking-[0.08em] text-brand-muted",
  2: "font-semibold uppercase tracking-[0.05em] text-brand-primary",
  3: "font-semibold text-brand-primary",
};
// Reader sizes scale with the reader's text setting; the survey gives them at 16px.
const READER_SIZE: Record<HeadingLevel, number> = { 1: 12 / 16, 2: 13.5 / 16, 3: 17 / 16 };
const READER_TAG = { 1: "h3", 2: "h4", 3: "h5" } as const;

// Space above and below each level, and between paragraphs: px on the card, multiples
// of the reader's text size in the reader.
const SPACE: Record<Surface, { heading: Record<HeadingLevel, [number, number]>; paragraph: number }> = {
  card: { heading: { 1: [20, 6], 2: [20, 6], 3: [18, 4] }, paragraph: 14 },
  reader: { heading: { 1: [1.9, 0.5], 2: [1.8, 0.45], 3: [1.5, 0.3] }, paragraph: 0.9 },
};

function length(surface: Surface, value: number): string {
  return surface === "card" ? `${value}px` : `calc(var(--reader-font-size) * ${value})`;
}

/** The space between `previous` and `block`. Below a heading it is that heading's own
 *  space below, so a stack keeps no space above its later headings. */
function gap(surface: Surface, previous: PassageBlock | undefined, block: PassageBlock): string {
  if (!previous) return "0";
  const space = SPACE[surface];
  if (previous.kind === "heading") return length(surface, space.heading[previous.level][1]);
  if (block.kind === "heading") return length(surface, space.heading[block.level][0]);
  return length(surface, space.paragraph);
}

/** `content[start, end)` with verse markers and the footnote markers given, each at its
 *  offset (one before `start` is drawn at the start). */
function textWithNotes(content: string, start: number, end: number, notes: Footnote[]): ReactNode {
  if (notes.length === 0) return renderVerseMarkers(content.slice(start, end));
  const local = notes.map((note) => ({ ...note, at: Math.max(0, Math.min(note.at, end) - start) }));
  return footnoteSegments(content.slice(start, end), local).map((segment, i) =>
    segment.kind === "text"
      ? <Fragment key={i}>{renderVerseMarkers(segment.text)}</Fragment>
      : <sup key={i} className="text-brand-accent" style={{ fontSize: 10 }}>{segment.n}</sup>,
  );
}

export function PassageBlocks({
  content,
  headings,
  footnotes = [],
  surface,
  className,
  style,
  id,
  hideChapterTitle = false,
  unitMarker,
}: {
  content: string;
  headings: PassageHeading[];
  footnotes?: Footnote[];
  surface: Surface;
  className?: string;
  style?: CSSProperties;
  id?: string;
  /** The reader, where the passage opens its chapter: a level-1 heading that repeats
   *  the chapter heading above it is left out. */
  hideChapterTitle?: boolean;
  /** The reader's `§N` superscript, set on the first paragraph after the headings. */
  unitMarker?: (paragraph: string) => ReactNode;
}) {
  const blocks = passageBlocks(content, headings);
  const notesFor = new Map<number, Footnote[]>();
  for (const note of footnotes) {
    const index = noteBlockIndex(blocks, note.at);
    notesFor.set(index, [...(notesFor.get(index) ?? []), note]);
  }
  const shown = blocks
    .map((block, index) => ({ block, index }))
    .filter(({ block }) => !(hideChapterTitle && block.kind === "heading" && block.level === 1
      && block.chapterTitle));
  const firstParagraph = shown.find(({ block }) => block.kind === "paragraph")?.index;

  return (
    <div id={id} className={className} style={style}>
      {shown.map(({ block, index }, i) => {
        const marginTop = gap(surface, shown[i - 1]?.block, block);
        const notes = notesFor.get(index) ?? [];
        if (block.kind === "heading") {
          // A pair is drawn as its label, " · " and its title. A note before the title
          // goes with the label, at its end if it sat in the label's dropped punctuation.
          const titleAt = block.parts[1]?.[0] ?? Infinity;
          const text = block.parts.map(([start, end], k) => (
            <Fragment key={k}>
              {k > 0 && " · "}
              {textWithNotes(content, start, end,
                notes.filter((note) => (k === 0 ? note.at < titleAt : note.at >= titleAt)))}
            </Fragment>
          ));
          if (surface === "card") {
            return <p key={index} className={CARD_CLASS[block.level]} style={{ marginTop }}>{text}</p>;
          }
          const Tag = READER_TAG[block.level];
          return (
            <Tag
              key={index}
              className={READER_CLASS[block.level]}
              style={{ marginTop, fontSize: length(surface, READER_SIZE[block.level]), lineHeight: 1.4 }}
            >
              {text}
            </Tag>
          );
        }
        const text = textWithNotes(content, block.start, block.end, notes);
        if (block.kind === "epigraph") {
          return surface === "card"
            ? (
              <p key={index} className="border-l-2 border-brand-muted/30 pl-3 text-[13px] text-brand-muted" style={{ marginTop }}>
                {text}
              </p>
            )
            : (
              <p
                key={index}
                className="italic text-brand-muted"
                style={{ marginTop, paddingLeft: "1.25em", fontSize: length(surface, 15 / 16) }}
              >
                {text}
              </p>
            );
        }
        return (
          <p key={index} className={surface === "card" ? "whitespace-pre-wrap" : undefined} style={{ marginTop }}>
            {index === firstParagraph && unitMarker?.(block.text)}
            {text}
          </p>
        );
      })}
    </div>
  );
}
