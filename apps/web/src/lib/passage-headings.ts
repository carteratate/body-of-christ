/**
 * Headings inside a passage (issue #445). Adapters keep a heading in the text of the
 * passage it introduces; the build marks it in `metadata.headings` as character offsets
 * of one whole paragraph of `content`, and the API sends the marks with the passage.
 * `content` never changes. A passage without marks is drawn exactly as before: there is
 * no heuristic, so a collection changes only when its marks arrive.
 *
 * - `role` "heading" with `level` 1 (a division the chapter label names), 2 (one tier
 *   below) or 3 (anything deeper), or "epigraph" (a scripture line under a heading).
 * - `pairs_next`: a level label printed on its own line before its title ("Article 1" /
 *   "THE REVELATION OF GOD"); the two show as one heading.
 * - `chapter_title`: a level-1 heading that repeats its chapter label, which the reader
 *   hides where the passage opens its chapter.
 */

export type HeadingLevel = 1 | 2 | 3;

export interface PassageHeading {
  at: number;
  end: number;
  role: "heading" | "epigraph";
  level?: HeadingLevel;
  pairs_next?: boolean;
  chapter_title?: boolean;
}

function parseOne(value: unknown, contentLength: number): PassageHeading | null {
  if (typeof value !== "object" || value === null) return null;
  const { at, end, role, level, pairs_next, chapter_title } = value as Record<string, unknown>;
  if (!Number.isInteger(at) || !Number.isInteger(end)) return null;
  if ((at as number) < 0 || (end as number) <= (at as number) || (end as number) > contentLength) return null;
  if (role === "epigraph") return { at: at as number, end: end as number, role };
  if (role !== "heading" || (level !== 1 && level !== 2 && level !== 3)) return null;
  return {
    at: at as number,
    end: end as number,
    role,
    level,
    ...(pairs_next === true ? { pairs_next: true } : {}),
    ...(chapter_title === true ? { chapter_title: true } : {}),
  };
}

/** The marks in `value`, in reading order. Anything malformed (not a list, an entry
 *  outside the content, overlapping marks) gives none, so a bad value can only show
 *  the passage as it was before #445. */
export function parseHeadings(value: unknown, content: string): PassageHeading[] {
  if (!Array.isArray(value) || value.length === 0) return [];
  const marks: PassageHeading[] = [];
  for (const item of value) {
    const mark = parseOne(item, content.length);
    if (!mark) return [];
    marks.push(mark);
  }
  marks.sort((a, b) => a.at - b.at);
  for (let i = 1; i < marks.length; i++) {
    if (marks[i - 1].end > marks[i].at) return [];
  }
  return marks;
}

export type PassageBlock =
  | {
    kind: "heading";
    level: HeadingLevel;
    start: number;
    end: number;
    /** The text shown: a pair's label and title joined ("Article 1 · The Revelation"). */
    text: string;
    /** The ranges of `content` drawn, joined by " · ": one, or a pair's label (without
     *  its trailing punctuation) and title. */
    parts: [number, number][];
    chapterTitle: boolean;
  }
  | { kind: "epigraph"; start: number; end: number; text: string }
  | { kind: "paragraph"; start: number; end: number; text: string };

/** The non-blank paragraphs of `content` between `from` and `to`, without the
 *  whitespace around them. */
function paragraphsIn(content: string, from: number, to: number): PassageBlock[] {
  const out: PassageBlock[] = [];
  const breaks = /\n[ \t]*\n/g;
  const slice = content.slice(from, to);
  // Paragraph bounds in pairs: [start, end, start, end, ...].
  const bounds = [from];
  for (let m = breaks.exec(slice); m; m = breaks.exec(slice)) {
    bounds.push(from + m.index, from + m.index + m[0].length);
  }
  bounds.push(to);
  for (let i = 0; i < bounds.length; i += 2) {
    const raw = content.slice(bounds[i], bounds[i + 1]);
    const text = raw.trim();
    if (!text) continue;
    const start = bounds[i] + (raw.length - raw.trimStart().length);
    out.push({ kind: "paragraph", start, end: start + text.length, text });
  }
  return out;
}

/** A level label without the punctuation that led into its title ("PART TWO:"). */
function labelText(text: string): string {
  return text.replace(/[\s:.,;—–-]+$/u, "");
}

/** `content` as blocks: its marked headings and epigraphs, and the paragraphs of the
 *  text between them. A `pairs_next` label and its title become one heading. */
export function passageBlocks(content: string, headings: PassageHeading[]): PassageBlock[] {
  const blocks: PassageBlock[] = [];
  let cursor = 0;
  for (let i = 0; i < headings.length; i++) {
    const mark = headings[i];
    blocks.push(...paragraphsIn(content, cursor, mark.at));
    const text = content.slice(mark.at, mark.end).trim();
    if (mark.role === "epigraph") {
      blocks.push({ kind: "epigraph", start: mark.at, end: mark.end, text });
      cursor = mark.end;
      continue;
    }
    const title = headings[i + 1];
    const paired = mark.pairs_next && title?.role === "heading" && title.level === mark.level
      && content.slice(mark.end, title.at).trim() === "";
    if (paired) {
      const label = labelText(text);
      blocks.push({
        kind: "heading",
        level: mark.level!,
        start: mark.at,
        end: title.end,
        text: `${label} · ${content.slice(title.at, title.end).trim()}`,
        parts: [[mark.at, mark.at + label.length], [title.at, title.end]],
        chapterTitle: !!(mark.chapter_title || title.chapter_title),
      });
      cursor = title.end;
      i++;
      continue;
    }
    blocks.push({
      kind: "heading", level: mark.level!, start: mark.at, end: mark.end, text,
      parts: [[mark.at, mark.end]],
      chapterTitle: !!mark.chapter_title,
    });
    cursor = mark.end;
  }
  blocks.push(...paragraphsIn(content, cursor, content.length));
  return blocks;
}

/** The block a footnote marker at `at` is drawn in: the first that ends at or after it,
 *  so each marker is drawn exactly once. */
export function noteBlockIndex(blocks: PassageBlock[], at: number): number {
  const index = blocks.findIndex((block) => at <= block.end);
  return index === -1 ? blocks.length - 1 : index;
}
