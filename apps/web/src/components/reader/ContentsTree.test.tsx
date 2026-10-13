// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ContentsNode } from "@/lib/api";
import { ContentsTree } from "./ContentsTree";

function node(key: string, label: string, chapter: string, children: ContentsNode[] = [], extra: Partial<ContentsNode> = {}): ContentsNode {
  return { key, kind: "article", label, short_label: label, chapter_key: chapter, anchor: null, range_label: null, children, ...extra };
}

const TREE = [
  node("I", "I · First Part", "i/q1/a1", [
    node("I/q1", "Q. 1 · Sacred Doctrine", "i/q1/a1", [
      node("I/q1/a1", "Art. 1 · Whether it is required?", "i/q1/a1"),
      node("I/q1/a2", "Art. 2 · Whether it is a science?", "i/q1/a2"),
    ], { kind: "question", range_label: "2 articles" }),
  ], { kind: "part", range_label: "Q. 1" }),
  node("I-II", "I-II · First Part of the Second Part", "ii/q1/a1", [
    node("I-II/q1", "Q. 1 · Of Man's Last End", "ii/q1/a1", [node("I-II/q1/a1", "Art. 1 · Whether man acts for an end?", "ii/q1/a1")], { kind: "question" }),
  ], { kind: "part" }),
];

afterEach(cleanup);

function items() {
  return screen.getAllByRole("treeitem").map((item) => within(item).getAllByText(/./)[0].textContent);
}

describe("ContentsTree", () => {
  it("shows the roots only, with their ranges", () => {
    render(<ContentsTree nodes={TREE} onOpen={vi.fn()} />);
    expect(items()).toEqual(["I · First Part", "I-II · First Part of the Second Part"]);
    expect(screen.getByText("Q. 1")).toBeTruthy();
    expect(screen.getAllByRole("treeitem")[0].getAttribute("aria-expanded")).toBe("false");
  });

  it("expands a grouping node when chosen instead of opening it", () => {
    const onOpen = vi.fn();
    render(<ContentsTree nodes={TREE} onOpen={onOpen} />);
    fireEvent.click(screen.getByText("I · First Part"));
    fireEvent.click(screen.getByText("Q. 1 · Sacred Doctrine"));
    expect(onOpen).not.toHaveBeenCalled();
    expect(items()).toContain("Art. 2 · Whether it is a science?");

    fireEvent.click(screen.getByText("Art. 2 · Whether it is a science?"));
    expect(onOpen).toHaveBeenCalledWith(TREE[0].children[0].children[1]);
  });

  it("opens the reader's branch and marks its place", () => {
    render(<ContentsTree nodes={TREE} currentKey="I/q1/a2" onOpen={vi.fn()} />);
    const current = screen.getByText("Art. 2 · Whether it is a science?").closest("[role=treeitem]")!;
    expect(current.getAttribute("aria-current")).toBe("location");
    expect(current.getAttribute("aria-level")).toBe("3");
    expect(current.getAttribute("tabindex")).toBe("0");
  });

  it("follows the ARIA tree keyboard pattern", () => {
    const onOpen = vi.fn();
    render(<ContentsTree nodes={TREE} onOpen={onOpen} />);
    const tree = screen.getByRole("tree");
    const first = screen.getAllByRole("treeitem")[0];
    first.focus();

    fireEvent.keyDown(tree, { key: "ArrowRight" });            // expand I
    expect(first.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(tree, { key: "ArrowRight" });            // move to Q. 1
    expect(document.activeElement?.textContent).toContain("Q. 1 · Sacred Doctrine");
    fireEvent.keyDown(tree, { key: "Enter" });                 // expands, does not open
    fireEvent.keyDown(tree, { key: "ArrowDown" });
    fireEvent.keyDown(tree, { key: "Enter" });                 // opens Art. 1
    expect(onOpen).toHaveBeenCalledWith(TREE[0].children[0].children[0]);
    fireEvent.keyDown(tree, { key: "ArrowLeft" });             // to parent Q. 1
    expect(document.activeElement?.textContent).toContain("Q. 1 · Sacred Doctrine");
    fireEvent.keyDown(tree, { key: "End" });
    expect(document.activeElement?.textContent).toContain("I-II · First Part of the Second Part");
    fireEvent.keyDown(tree, { key: "Home" });
    expect(document.activeElement?.textContent).toContain("I · First Part");
  });

  it("filters to matches with their ancestors, and expands a matching group to all its children", () => {
    const onOpen = vi.fn();
    render(<ContentsTree nodes={TREE} filter="last end" onOpen={onOpen} />);
    expect(items()).toEqual(["I-II · First Part of the Second Part", "Q. 1 · Of Man's Last End"]);
    fireEvent.click(screen.getByText("Q. 1 · Of Man's Last End"));
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Art. 1 · Whether man acts for an end?"));
    expect(onOpen).toHaveBeenCalledWith(TREE[1].children[0].children[0]);
  });

  it("never opens a node from its chevron, filtered or not", () => {
    const onOpen = vi.fn();
    const { rerender } = render(<ContentsTree nodes={TREE} onOpen={onOpen} />);
    const chevron = (label: string) => screen.getByText(label).closest("[role=treeitem]")!.querySelector("svg")!.parentElement!;
    fireEvent.click(chevron("I · First Part"));
    expect(items()).toContain("Q. 1 · Sacred Doctrine");

    rerender(<ContentsTree nodes={TREE} filter="science" onOpen={onOpen} />);
    fireEvent.click(chevron("I · First Part"));                 // collapses the filtered path
    expect(items()).toEqual(["I · First Part"]);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("shows the match cap's note", () => {
    const many = Array.from({ length: 205 }, (_, i) => node(`n${i}`, `Whether ${i}`, `c${i}`));
    render(<ContentsTree nodes={many} filter="whether" onOpen={vi.fn()} />);
    expect(screen.getAllByRole("treeitem")).toHaveLength(200);
    expect(screen.getByText(/Showing the first 200 matches/)).toBeTruthy();
  });

  it("finds a paragraph number inside a heading's range", () => {
    const ccc = [node("article-4", "Article 4 · Penance", "ccc/a4", [
      node("h1", "I. What Is This Sacrament Called?", "ccc/a4", [], { kind: "heading", anchor: "ccc/1423", range_label: "§§1423–1424" }),
      node("h10", "X. Indulgences", "ccc/a4", [], { kind: "heading", anchor: "ccc/1471", range_label: "§§1471–1479" }),
    ], { range_label: "§§1422–1498" })];
    render(<ContentsTree nodes={ccc} filter="1471" onOpen={vi.fn()} />);
    expect(items()).toEqual(["Article 4 · Penance", "X. Indulgences"]);
  });

  it("says when nothing matches", () => {
    render(<ContentsTree nodes={TREE} filter="purgatory" onOpen={vi.fn()} />);
    expect(screen.getByText("Nothing in the contents matches that search.")).toBeTruthy();
  });

  it("renders only expanded branches of a large tree", () => {
    const large = Array.from({ length: 6 }, (_, p) => node(`p${p}`, `Part ${p}`, `c${p}/0`,
      Array.from({ length: 100 }, (_, q) => node(`p${p}/q${q}`, `Question ${q}`, `c${p}/${q}`,
        Array.from({ length: 5 }, (_, a) => node(`p${p}/q${q}/a${a}`, `Article ${a}`, `c${p}/${q}/${a}`)),
        { kind: "question" })), { kind: "part" }));
    render(<ContentsTree nodes={large} onOpen={vi.fn()} />);
    expect(screen.getAllByRole("treeitem")).toHaveLength(6);
    fireEvent.click(screen.getByText("Part 2"));
    expect(screen.getAllByRole("treeitem")).toHaveLength(106);
  });
});
