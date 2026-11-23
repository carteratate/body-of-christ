import { describe, expect, it } from "vitest";

import { noteBlockIndex, parseHeadings, passageBlocks } from "./passage-headings";

const CCC = "Article 1\n\nTHE REVELATION OF GOD\n\n\"You shall not kill.\"\n\nGod reveals himself.\n\nA second paragraph.";
const CCC_MARKS = [
  { at: 0, end: 9, role: "heading", level: 1, pairs_next: true, chapter_title: true },
  { at: 11, end: 32, role: "heading", level: 1 },
  { at: 34, end: 55, role: "epigraph" },
];

describe("parseHeadings", () => {
  it("keeps well-formed marks in reading order and drops unknown keys", () => {
    expect(parseHeadings([CCC_MARKS[2], { ...CCC_MARKS[1], colour: "red" }], CCC)).toEqual([
      { at: 11, end: 32, role: "heading", level: 1 },
      { at: 34, end: 55, role: "epigraph" },
    ]);
  });

  it.each([
    ["not a list", { at: 0 }],
    ["an entry past the content", [{ at: 0, end: 999, role: "heading", level: 1 }]],
    ["an empty span", [{ at: 3, end: 3, role: "heading", level: 1 }]],
    ["a level out of range", [{ at: 0, end: 9, role: "heading", level: 4 }]],
    ["an unknown role", [{ at: 0, end: 9, role: "caption" }]],
    ["overlapping marks", [{ at: 0, end: 12, role: "heading", level: 1 }, { at: 11, end: 32, role: "heading", level: 2 }]],
  ])("gives none for %s", (_, value) => {
    expect(parseHeadings(value, CCC)).toEqual([]);
  });

  it("gives none when absent", () => {
    expect(parseHeadings(undefined, CCC)).toEqual([]);
    expect(parseHeadings([], CCC)).toEqual([]);
  });
});

describe("passageBlocks", () => {
  it("joins a pair into one heading and splits the text between marks into paragraphs", () => {
    const blocks = passageBlocks(CCC, parseHeadings(CCC_MARKS, CCC));
    expect(blocks.map((b) => [b.kind, b.text])).toEqual([
      ["heading", "Article 1 · THE REVELATION OF GOD"],
      ["epigraph", "\"You shall not kill.\""],
      ["paragraph", "God reveals himself."],
      ["paragraph", "A second paragraph."],
    ]);
    expect(blocks[0]).toMatchObject({ level: 1, chapterTitle: true, start: 0, end: 32 });
  });

  it("drops a level label's trailing punctuation when it joins its title", () => {
    const content = "PART TWO:\n\nTHE CELEBRATION\n\nText.";
    const marks = parseHeadings([
      { at: 0, end: 9, role: "heading", level: 1, pairs_next: true },
      { at: 11, end: 26, role: "heading", level: 1 },
    ], content);
    expect(passageBlocks(content, marks)[0].text).toBe("PART TWO · THE CELEBRATION");
  });

  it("keeps an unpaired label as its own heading", () => {
    const content = "Article 1\n\nThe title\n\nText.";
    const marks = parseHeadings([
      { at: 0, end: 9, role: "heading", level: 1, pairs_next: true },
      { at: 11, end: 20, role: "heading", level: 2 },
    ], content);
    expect(passageBlocks(content, marks).map((b) => b.kind)).toEqual(["heading", "heading", "paragraph"]);
  });

  it("places each footnote marker in exactly one block", () => {
    const blocks = passageBlocks(CCC, parseHeadings(CCC_MARKS, CCC));
    expect(noteBlockIndex(blocks, 32)).toBe(0);
    expect(noteBlockIndex(blocks, 33)).toBe(1);
    expect(noteBlockIndex(blocks, CCC.length)).toBe(3);
  });
});
