/**
 * A passage's footnotes (issue #279). The USCCB requires footnoted material in a
 * Catechism excerpt to be identified, so a passage carries its notes beside its text:
 * `n` is the Catechism's own note number (never renumbered), `at` the character
 * offset in `content` where its marker sits. Notes are never part of `content`.
 */
export interface Footnote {
  n: number;
  text: string;
  at: number;
}

function isFootnote(value: unknown, contentLength: number): value is Footnote {
  if (typeof value !== "object" || value === null) return false;
  const { n, text, at } = value as Record<string, unknown>;
  return (
    Number.isInteger(n) && (n as number) > 0
    && typeof text === "string" && text.trim() !== ""
    && Number.isInteger(at) && (at as number) >= 0 && (at as number) <= contentLength
  );
}

/** The usable notes in `value`, in marker order. Entries whose `at` falls outside
 *  `0..content.length`, or that are malformed, are dropped; anything that is not a
 *  list gives none. */
export function parseFootnotes(value: unknown, content: string): Footnote[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Footnote => isFootnote(item, content.length))
    .map(({ n, text, at }) => ({ n, text, at }))
    .sort((a, b) => a.at - b.at);
}

export type FootnoteSegment =
  | { kind: "text"; text: string }
  | { kind: "marker"; n: number };

/** `content` cut at each marker's offset, for rendering superscripts in place. */
export function footnoteSegments(content: string, footnotes: Footnote[]): FootnoteSegment[] {
  const segments: FootnoteSegment[] = [];
  let cursor = 0;
  for (const note of footnotes) {
    if (note.at > cursor) segments.push({ kind: "text", text: content.slice(cursor, note.at) });
    segments.push({ kind: "marker", n: note.n });
    cursor = Math.max(cursor, note.at);
  }
  if (cursor < content.length) segments.push({ kind: "text", text: content.slice(cursor) });
  return segments;
}

const SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹";

function superscript(n: number): string {
  return String(n).replace(/\d/g, (digit) => SUPERSCRIPT_DIGITS[Number(digit)]);
}

/** Plain text for the clipboard: the passage with its markers in superscript digits,
 *  so a copied note can still be matched to its place without brackets that would
 *  read as the Catechism's own in-text citations. */
export function contentWithMarkers(content: string, footnotes: Footnote[]): string {
  return footnoteSegments(content, footnotes)
    .map((segment) => (segment.kind === "text" ? segment.text : superscript(segment.n)))
    .join("");
}

/** The notes block for the clipboard ("Notes:" then one per line), or "" for none. */
export function footnotesCopyText(footnotes: Footnote[]): string {
  if (!footnotes.length) return "";
  return ["Notes:", ...footnotes.map((note) => `${note.n}. ${note.text}`)].join("\n");
}
