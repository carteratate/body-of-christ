import { describe, expect, it } from "vitest";

import {
  contentWithMarkers,
  footnoteSegments,
  footnotesCopyText,
  parseFootnotes,
} from "./footnotes";

const CONTENT = "The death penalty is inadmissible.";

describe("parseFootnotes", () => {
  it("keeps valid notes in marker order", () => {
    expect(parseFootnotes([
      { n: 68, text: "Second", at: CONTENT.length },
      { n: 67, text: "First", at: 3 },
    ], CONTENT)).toEqual([
      { n: 67, text: "First", at: 3 },
      { n: 68, text: "Second", at: CONTENT.length },
    ]);
  });

  it("drops entries whose offset is outside the content, and malformed ones", () => {
    expect(parseFootnotes([
      { n: 1, text: "Past the end", at: CONTENT.length + 1 },
      { n: 2, text: "Negative", at: -1 },
      { n: 3, text: "", at: 0 },
      { n: 4.5, text: "Fractional", at: 0 },
      "not a note",
      { n: 5, text: "Kept", at: 0 },
    ], CONTENT)).toEqual([{ n: 5, text: "Kept", at: 0 }]);
  });

  it("gives no notes for anything that is not a list", () => {
    expect(parseFootnotes(undefined, CONTENT)).toEqual([]);
    expect(parseFootnotes({ n: 1, text: "x", at: 0 }, CONTENT)).toEqual([]);
  });
});

describe("footnote text", () => {
  const notes = [{ n: 67, text: "First", at: 3 }, { n: 68, text: "Second", at: CONTENT.length }];

  it("cuts the content at each marker", () => {
    expect(footnoteSegments(CONTENT, notes)).toEqual([
      { kind: "text", text: "The" },
      { kind: "marker", n: 67 },
      { kind: "text", text: CONTENT.slice(3) },
      { kind: "marker", n: 68 },
    ]);
  });

  it("writes markers as superscript digits for the clipboard", () => {
    expect(contentWithMarkers(CONTENT, notes)).toBe(`The⁶⁷${CONTENT.slice(3)}⁶⁸`);
  });

  it("lists the notes under a Notes heading, one per line", () => {
    expect(footnotesCopyText(notes)).toBe("Notes:\n67. First\n68. Second");
    expect(footnotesCopyText([])).toBe("");
  });
});
