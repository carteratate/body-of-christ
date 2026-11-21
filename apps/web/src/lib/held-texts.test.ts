import { describe, expect, it } from "vitest";
import type { HeldText, TocEntry } from "@/lib/api";
import { heldAfter, heldBeforeFirst, heldCountLabel, placeHeldTexts } from "./held-texts";

const chapters: TocEntry[] = [
  { chapter_key: "s8", chapter_label: "Session 8" },
  { chapter_key: "s13", chapter_label: "Session 13" },
  { chapter_key: "s15", chapter_label: "Session 15" },
];

function held(key: string, after: [string, string] | null): HeldText {
  return {
    key, label: key, heading: `Heading ${key}`,
    after_anchor: after?.[0] ?? null, after_chapter_key: after?.[1] ?? null,
    url: "https://example.org/held",
  };
}

const list = [
  held("s1", null), held("s3", null),
  held("s12", ["s8/2", "s8"]),
  held("s14", ["s13/1", "s13"]), held("s15a", ["s13/1", "s13"]),
  held("s45", ["s15/9", "s15"]),
];

describe("placeHeldTexts", () => {
  it("puts each held text after its chapter, the first ones first, in file order", () => {
    const placed = placeHeldTexts(chapters, list).map((e) => (e.kind === "chapter" ? `#${e.ordinal} ${e.entry.chapter_key}` : e.held.key));
    expect(placed).toEqual(["s1", "s3", "#1 s8", "s12", "#2 s13", "s14", "s15a", "#3 s15", "s45"]);
  });

  it("is today's chapter list without held texts", () => {
    expect(placeHeldTexts(chapters)).toEqual(chapters.map((entry, index) => ({ kind: "chapter", entry, ordinal: index + 1 })));
    expect(placeHeldTexts(chapters, [])).toHaveLength(3);
  });

  it("keeps a held text whose chapter is not listed, at the end", () => {
    const placed = placeHeldTexts(chapters, [held("x", ["s99/1", "s99"]), held("s1", null)]);
    expect(placed.map((e) => (e.kind === "held" ? e.held.key : e.entry.chapter_key))).toEqual(["s1", "s8", "s13", "s15", "x"]);
  });

  it("shows a repeated chapter key's held texts once", () => {
    const repeated = [...chapters, { chapter_key: "s8", chapter_label: "Session 8 again" }];
    expect(placeHeldTexts(repeated, list).filter((e) => e.kind === "held" && e.held.key === "s12")).toHaveLength(1);
  });
});

describe("heldAfter and heldBeforeFirst", () => {
  it("finds the held texts after one passage, in order", () => {
    expect(heldAfter("s13/1", list).map((h) => h.key)).toEqual(["s14", "s15a"]);
    expect(heldAfter("s13/2", list)).toEqual([]);
    expect(heldAfter("s13/1")).toEqual([]);
  });

  it("finds the held texts before every passage", () => {
    expect(heldBeforeFirst(list).map((h) => h.key)).toEqual(["s1", "s3"]);
  });
});

describe("heldCountLabel", () => {
  it("counts texts", () => {
    expect(heldCountLabel(1)).toBe("1 text read online");
    expect(heldCountLabel(17)).toBe("17 texts read online");
  });
});
