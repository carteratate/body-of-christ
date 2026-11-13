// @vitest-environment jsdom

// Corpus cleanup 2.4d: the reader labels a passage that states a position its document
// rejects, and renders every other passage as before.

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Passage } from "./Passage";
import type { ReaderPassage } from "@/lib/api";

afterEach(cleanup);

const LABEL = "Condemned proposition 31 (condemned by Leo X, Exsurge Domine)";
const TEXT = "In every good work the just man sins.";

function passage(overrides: Partial<ReaderPassage> = {}): ReaderPassage {
  return {
    id: "00000000-0000-0000-0000-000000000031",
    anchor: "exsurge-domine/31",
    chapter_key: "exsurge-domine",
    chapter_label: "Exsurge Domine",
    unit_label: LABEL,
    reference: "Pope Leo X — Exsurge Domine, §31",
    content: TEXT,
    voice: "rejected",
    ...overrides,
  };
}

describe("Passage", () => {
  it("sets a rejected passage off as a quotation under a caption, not an inline marker", () => {
    const { container } = render(<Passage passage={passage()} highlighted={false} />);
    const caption = screen.getByText(LABEL).closest("p")!;
    expect(caption.textContent).toBe(`${LABEL} · a position the document rejects`);
    const quoted = screen.getByText(TEXT).closest("[data-voice='rejected']")!;
    expect(quoted.className).toContain("border-l-2");
    expect(caption.compareDocumentPosition(quoted) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector("sup")).toBeNull();
  });

  it("renders exactly as today without the field", () => {
    // Recorded from master's Passage, before 2.4d.
    const { container } = render(<Passage passage={passage({ voice: undefined })} highlighted />);
    expect(container.innerHTML).toMatchSnapshot();
  });
});

describe("Passage text labels (corpus cleanup 2.4f)", () => {
  const LATIN = "https://www.vatican.va/content/francesco/la/motu_proprio/documents/papa-francesco-motu-proprio_20150815_de-concordia-inter-codices.html";
  const plain = { unit_label: null, voice: undefined, content: "Only those marriages are valid…" };

  it("shows the unofficial-English line under the text, Latin linked", () => {
    render(<Passage passage={passage({ ...plain, text_status: "unofficial_english", official_latin_url: LATIN })} highlighted={false} />);
    const label = screen.getByTestId("text-label");
    expect(label.textContent).toMatch(/^Unofficial English translation \(L’Osservatore Romano\)\. The Latin text is official/);
    expect(label.closest("div")!.className).toContain("text-brand-muted");
    expect(screen.getByRole("link", { name: /The Latin text is official/ }).getAttribute("href")).toBe(LATIN);
    const text = screen.getByText(plain.content);
    expect(text.compareDocumentPosition(label) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the scanned-edition label", () => {
    render(<Passage passage={passage({ ...plain, text_source: "ocr" })} highlighted={false} />);
    expect(screen.getByTestId("text-label").textContent).toBe("Text from a scanned edition");
  });

  it("adds nothing without the fields", () => {
    const { container } = render(<Passage passage={passage(plain)} highlighted={false} />);
    expect(screen.queryByTestId("text-label")).toBeNull();
    expect(container.querySelectorAll("p")).toHaveLength(1);
  });
});
