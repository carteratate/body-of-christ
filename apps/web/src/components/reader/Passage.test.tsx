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
