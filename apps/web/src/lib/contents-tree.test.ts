import { describe, expect, it } from "vitest";

import type { ContentsNode } from "@/lib/api";
import {
  ancestorKeys,
  countByKind,
  indexContents,
  matchingKeys,
  nodeForChapter,
  opensOwnContent,
  pathKeys,
  visibleRows,
} from "./contents-tree";

function node(key: string, chapter: string, children: ContentsNode[] = [], extra: Partial<ContentsNode> = {}): ContentsNode {
  return {
    key, kind: "article", label: key, short_label: key, chapter_key: chapter,
    anchor: null, range_label: null, children, ...extra,
  };
}

// I > Q1 > (A1, A2); II > Q1 > A1. Parts and questions only group their articles.
const SUMMA = [
  node("I", "i/q1/a1", [
    node("I/q1", "i/q1/a1", [node("I/q1/a1", "i/q1/a1"), node("I/q1/a2", "i/q1/a2", [], { short_label: "Art. 2 · Whether sacred doctrine is a science?" })],
      { kind: "question", short_label: "Q. 1 · Sacred Doctrine" }),
  ], { kind: "part", short_label: "I · First Part" }),
  node("I-II", "ii/q1/a1", [
    node("I-II/q1", "ii/q1/a1", [node("I-II/q1/a1", "ii/q1/a1")], { kind: "question", short_label: "Q. 1 · Of Man's Last End" }),
  ], { kind: "part", short_label: "I-II · First Part of the Second Part" }),
];

// A Catechism article with its own text and two headings inside it.
const CATECHISM = [
  node("part-2", "ccc/a4", [
    node("article-4", "ccc/a4", [
      node("h1", "ccc/a4", [], { kind: "heading", anchor: "ccc/1423", range_label: "§§1423–1424" }),
      node("h10", "ccc/a4", [], { kind: "heading", anchor: "ccc/1471", range_label: "§§1471–1479" }),
    ], { range_label: "§§1422–1498", short_label: "Article 4 · Penance" }),
  ], { kind: "part", range_label: "§§1066–1690" }),
];

describe("contents tree logic", () => {
  it("indexes levels, positions and parents", () => {
    const index = indexContents(SUMMA);
    expect(index.get("I/q1/a2")).toMatchObject({ parentKey: "I/q1", level: 3, posInSet: 2, setSize: 2 });
    expect(ancestorKeys(index, "I/q1/a2")).toEqual(["I/q1", "I"]);
  });

  it("shows roots only until a branch is expanded", () => {
    const index = indexContents(SUMMA);
    expect(visibleRows(SUMMA, index, new Set(), null).rows.map((r) => r.node.key)).toEqual(["I", "I-II"]);
    expect(visibleRows(SUMMA, index, new Set(["I", "I/q1"]), null).rows.map((r) => r.node.key))
      .toEqual(["I", "I/q1", "I/q1/a1", "I/q1/a2", "I-II"]);
  });

  it("filters to matches and their ancestors, opening the way to them", () => {
    const index = indexContents(SUMMA);
    const matches = matchingKeys(index, "science");
    const { rows } = visibleRows(SUMMA, index, pathKeys(index, matches), matches);
    expect(rows.map((r) => [r.node.key, r.expanded, r.matched])).toEqual([
      ["I", true, false], ["I/q1", true, false], ["I/q1/a2", false, true],
    ]);
  });

  it("lists every child of a matching node the reader expands", () => {
    const index = indexContents(SUMMA);
    const matches = matchingKeys(index, "1 · sacred");      // the question, not its articles
    const seeded = pathKeys(index, matches);
    expect(visibleRows(SUMMA, index, seeded, matches).rows.map((r) => r.node.key)).toEqual(["I", "I/q1"]);
    const opened = new Set([...seeded, "I/q1"]);
    expect(visibleRows(SUMMA, index, opened, matches).rows.map((r) => r.node.key))
      .toEqual(["I", "I/q1", "I/q1/a1", "I/q1/a2"]);
  });

  it("drops a branch the match cap leaves empty", () => {
    const tree = [
      node("A", "a1", [node("A/1", "a1", [], { short_label: "Whether" })], { kind: "part" }),
      node("B", "b1", [node("B/1", "b1", [], { short_label: "Whether" })], { kind: "part" }),
    ];
    const index = indexContents(tree);
    const matches = matchingKeys(index, "whether");
    const { rows, truncated } = visibleRows(tree, index, pathKeys(index, matches), matches, 1);
    expect(rows.map((r) => r.node.key)).toEqual(["A", "A/1"]);
    expect(truncated).toBe(true);
  });

  it("matches without case or accents", () => {
    const index = indexContents([node("a", "c", [], { short_label: "De Trinitáte" })]);
    expect([...matchingKeys(index, "TRINITATE")]).toEqual(["a"]);
  });

  it("matches a paragraph number by range when the tree has paragraph ranges", () => {
    const index = indexContents(CATECHISM);
    expect([...matchingKeys(index, "1471")]).toEqual(["part-2", "article-4", "h10"]);
  });

  it("caps the matches it shows", () => {
    const many = Array.from({ length: 5 }, (_, i) => node(`n${i}`, `c${i}`, [], { short_label: "Whether" }));
    const index = indexContents(many);
    const { rows, truncated } = visibleRows(many, index, new Set(), matchingKeys(index, "whether"), 3);
    expect(rows).toHaveLength(3);
    expect(truncated).toBe(true);
  });

  it("knows which nodes only group their children", () => {
    expect(opensOwnContent(SUMMA[0])).toBe(false);            // a Part opens its first article
    expect(opensOwnContent(SUMMA[0].children[0])).toBe(false);
    expect(opensOwnContent(SUMMA[0].children[0].children[0])).toBe(true);
    expect(opensOwnContent(CATECHISM[0].children[0])).toBe(true); // headings point inside it
  });

  it("finds the reader's place and counts kinds", () => {
    expect(nodeForChapter(SUMMA, "i/q1/a1")?.key).toBe("I/q1/a1");
    expect(nodeForChapter(CATECHISM, "ccc/a4")?.key).toBe("article-4");
    expect(nodeForChapter(SUMMA, "nowhere")).toBeNull();
    expect([...countByKind(SUMMA)]).toEqual([["part", 2], ["question", 2], ["article", 3]]);
  });
});
