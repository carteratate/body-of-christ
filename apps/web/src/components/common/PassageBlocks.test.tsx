// @vitest-environment jsdom

// Issue #445: headings marked inside a passage are set apart on the card and in the
// reader, and a passage without marks is drawn exactly as before.

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PassageText } from "./PassageText";
import { Passage } from "@/components/reader/Passage";
import type { ReaderPassage } from "@/lib/api";
import { parseHeadings } from "@/lib/passage-headings";

afterEach(cleanup);

const GS = "CHAPTER V\n\nSECTION 1 The Avoidance of War\n\nEven though recent wars have wrought physical havoc.\n\nA second paragraph.";
const GS_MARKS = [
  { at: 0, end: 9, role: "heading", level: 1, chapter_title: true },
  { at: 11, end: 41, role: "heading", level: 2 },
];

function reader(overrides: Partial<ReaderPassage> = {}): ReaderPassage {
  return {
    id: "p79", anchor: "gs/79", chapter_key: "c5", chapter_label: "Chapter V",
    unit_label: "§79", reference: "Gaudium et Spes, §79", content: GS, headings: GS_MARKS,
    ...overrides,
  };
}

describe("PassageText with headings", () => {
  it("draws an unmarked passage as the single paragraph it has always been", () => {
    const { container: plain } = render(<PassageText content={GS} footnotes={[]} />);
    const { container: none } = render(<PassageText content={GS} footnotes={[]} headings={[]} />);
    expect(none.innerHTML).toBe(plain.innerHTML);
    expect(plain.querySelectorAll("p")).toHaveLength(1);
    expect(plain.querySelector("p")!.className).toBe("text-sm text-brand-primary leading-relaxed whitespace-pre-wrap");
  });

  it("sets each level apart on the card, as styled paragraphs rather than headings", () => {
    const { container } = render(
      <PassageText content={GS} footnotes={[]} headings={parseHeadings(GS_MARKS, GS)} />,
    );
    expect(container.querySelectorAll("h3, h4, h5")).toHaveLength(0);
    const level1 = screen.getByText("CHAPTER V");
    expect(level1.className).toContain("uppercase");
    expect(level1.className).toContain("text-brand-muted");
    const level2 = screen.getByText("SECTION 1 The Avoidance of War");
    expect(level2.className).toContain("text-[12.5px]");
    // Stacked: the second heading sits at the first's space below, not its own above.
    expect(level2.style.marginTop).toBe("6px");
    expect(screen.getByText("A second paragraph.").style.marginTop).toBe("14px");
  });

  it("keeps footnote markers in place inside a marked passage", () => {
    const at = GS.indexOf(" havoc") + " havoc.".length;
    const { container } = render(
      <PassageText content={GS} footnotes={[{ n: 7, text: "Note.", at }]} headings={parseHeadings(GS_MARKS, GS)} />,
    );
    const sup = container.querySelector("sup")!;
    expect(sup.textContent).toBe("7");
    expect(sup.closest("p")!.textContent).toBe("Even though recent wars have wrought physical havoc.7");
  });

  it("draws an epigraph inset under a rule", () => {
    const content = "Legitimate defense\n\n\"You shall not kill.\"\n\nText.";
    render(<PassageText content={content} footnotes={[]} headings={parseHeadings([
      { at: 0, end: 18, role: "heading", level: 3 }, { at: 20, end: 41, role: "epigraph" },
    ], content)} />);
    const epigraph = screen.getByText("\"You shall not kill.\"");
    expect(epigraph.className).toContain("border-l-2");
    expect(screen.getByText("Legitimate defense").className).not.toContain("uppercase");
  });
});

describe("paired headings", () => {
  const content = "Article 1\n\nTHE REVELATION OF GOD\n\nText.";
  const marks = [
    { at: 0, end: 9, role: "heading", level: 1, pairs_next: true },
    { at: 11, end: 32, role: "heading", level: 1 },
  ];

  it("draws a label and its title as one heading joined by a dot", () => {
    const { container } = render(<PassageText content={content} footnotes={[]} headings={parseHeadings(marks, content)} />);
    expect(container.querySelector("p")!.textContent).toBe("Article 1 · THE REVELATION OF GOD");
  });

  it("keeps a note in the title with the title", () => {
    const { container } = render(
      <PassageText content={content} footnotes={[{ n: 3, text: "N.", at: 32 }]} headings={parseHeadings(marks, content)} />,
    );
    expect(container.querySelector("p")!.textContent).toBe("Article 1 · THE REVELATION OF GOD3");
  });
});

describe("Passage (reader) with headings", () => {
  it("renders headings as h3 to h5 and moves the unit marker to the first paragraph", () => {
    const { container } = render(<Passage passage={reader()} highlighted={false} />);
    expect(container.querySelector("h3")!.textContent).toBe("CHAPTER V");
    expect(container.querySelector("h4")!.textContent).toBe("SECTION 1 The Avoidance of War");
    const sup = container.querySelector("sup")!;
    expect(sup.textContent).toBe("§79");
    expect(sup.closest("p")!.textContent).toContain("Even though recent wars");
    expect(container.querySelector("#anchor-gs\\/79")).not.toBeNull();
  });

  it("hides a chapter-title heading where the passage opens its chapter", () => {
    const { container } = render(<Passage passage={reader()} highlighted={false} opensChapter />);
    expect(container.querySelector("h3")).toBeNull();
    expect(container.querySelector("h4")!.style.marginTop).toBe("0px");
  });

  it("draws an unmarked reader passage exactly as before", () => {
    const plain = reader({ headings: undefined });
    const { container } = render(<Passage passage={plain} highlighted={false} opensChapter />);
    const p = container.querySelector("#anchor-gs\\/79")!;
    expect(p.tagName).toBe("P");
    expect(p.textContent).toBe(`§79${GS}`);
    expect(container.querySelectorAll("h3, h4, h5")).toHaveLength(0);
  });
});
