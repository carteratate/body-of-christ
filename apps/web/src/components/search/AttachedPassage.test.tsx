// @vitest-environment jsdom

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AttachedPassage } from "./AttachedPassage";
import type { AttachedContext } from "@/lib/api";

afterEach(cleanup);

function context(relation: "answered_by" | "answers", parts: Partial<AttachedContext["parts"][0]>[]): AttachedContext {
  return {
    relation,
    parts: parts.map((part, index) => ({
      content: `part ${index}`,
      reference: "ST I q1 a1",
      unit_label: null,
      anchor: `a/${index}`,
      ...part,
    })),
  };
}

/**
 * The text of the element that actually labels the region.
 *
 * Resolved through `aria-labelledby` rather than read off the aside's textContent: the
 * aside also contains the junction marker ("↓ Aquinas replies below"), so asserting a
 * direction over the whole subtree is satisfied by a different element than the one
 * under test — which is how a boundary label with no direction at all once passed.
 */
function boundaryLabel(): string {
  const aside = screen.getByRole("complementary");
  const id = aside.getAttribute("aria-labelledby");
  if (!id) throw new Error("aside is not labelled by any element");
  return document.getElementById(id)?.textContent ?? "";
}

describe("AttachedPassage", () => {
  it("names the attached passage as Aquinas's answer to the objection", () => {
    // The matched passage is a position he REFUTES; a boundary that failed to say so
    // would leave the card reading as one continuous argument in his voice.
    render(<AttachedPassage context={context("answered_by", [{ content: "I answer that..." }])} color="#fff" rgb="255,255,255" />);

    expect(boundaryLabel()).toMatch(/Aquinas answers/);
    expect(screen.getByText("I answer that...")).toBeTruthy();
  });

  it("says the attached objection is answered below, not merely which objection it is", () => {
    // On a reply card the objection is read FIRST. A label naming it without stating the
    // direction reproduces the misattribution one position higher: the reader meets a
    // position Aquinas rejects with nothing yet saying he rejects it. The assertion is on
    // the PROPERTY — that a direction is stated — so any wording carrying one passes.
    render(<AttachedPassage context={context("answers", [{ content: "It would seem...", unit_label: "Objection 2" }])} color="#fff" rgb="255,255,255" />);

    expect(boundaryLabel()).toMatch(/Objection 2/);
    expect(boundaryLabel()).toMatch(/below/i);
  });

  it("marks the junction where the objection ends and the reply begins", () => {
    // The opening label is at the very top of the card and an objection can outrun a
    // phone viewport, so the two voices must be separated where they actually meet.
    render(<AttachedPassage context={context("answers", [{ content: "It would seem...", unit_label: "Objection 2" }])} color="#fff" rgb="255,255,255" />);

    expect(screen.getByText(/Aquinas replies below/)).toBeTruthy();
  });

  it("puts no junction marker on an objection card, where the match comes first", () => {
    render(<AttachedPassage context={context("answered_by", [{ content: "I answer that..." }])} color="#fff" rgb="255,255,255" />);

    expect(screen.queryByText(/replies below/)).toBeNull();
  });

  it("still states the direction when the corpus left the passage unlabelled", () => {
    render(<AttachedPassage context={context("answers", [{ content: "It would seem...", unit_label: null }])} color="#fff" rgb="255,255,255" />);

    expect(boundaryLabel()).toMatch(/below/i);
  });

  it("renders every part of a split answer in the order given", () => {
    // 109 articles split the determination across chunks; showing only the first would
    // present half an answer as the whole of it.
    const { container } = render(
      <AttachedPassage
        context={context("answered_by", [{ content: "first half" }, { content: "second half" }])}
        color="#fff"
        rgb="255,255,255"
      />,
    );

    const paragraphs = Array.from(container.querySelectorAll("p")).map((p) => p.textContent);
    expect(paragraphs).toEqual(["first half", "second half"]);
  });

  it("exposes the attachment as a labelled aside rather than unmarked prose", () => {
    render(<AttachedPassage context={context("answered_by", [{ content: "I answer that..." }])} color="#fff" rgb="255,255,255" />);

    const aside = screen.getByRole("complementary", { name: /Aquinas answers/ });
    expect(within(aside).getByText("I answer that...")).toBeTruthy();
  });

  it("preserves the paragraph breaks inside an attached passage", () => {
    // A determination runs to ~12,000 characters across several paragraphs. Collapsed
    // into one block it becomes a wall of text, and the answer stops being readable at
    // exactly the length where reading it matters most.
    const { container } = render(
      <AttachedPassage context={context("answered_by", [{ content: "first\n\nsecond" }])} color="#fff" rgb="255,255,255" />,
    );

    // Asserted on the class rather than the computed style: jsdom loads no Tailwind, so
    // getComputedStyle reports nothing for a utility class.
    expect(container.querySelector("p")!.className).toContain("whitespace-pre-wrap");
  });

  it("renders verse markers rather than printing their raw syntax", () => {
    render(
      <AttachedPassage context={context("answered_by", [{ content: "As it says {{v:3}} in scripture" }])} color="#fff" rgb="255,255,255" />,
    );

    expect(screen.queryByText(/\{\{v:3\}\}/)).toBeNull();
  });

  it("keeps the boundary label on a themed colour, not the collection palette", () => {
    // globals.css themes --color-brand-* for the light theme but NOT
    // --color-collection-*, so a collection colour here renders at ~1.4:1 in light mode.
    // Elsewhere that palette is decorative; this label is the safety mechanism.
    render(<AttachedPassage context={context("answered_by", [{ content: "I answer that..." }])} color="#55cc88" rgb="85,204,136" />);

    const aside = screen.getByRole("complementary");
    const label = document.getElementById(aside.getAttribute("aria-labelledby")!)!;
    expect(label.style.color).toBe("");
  });

  it("renders nothing when there are no parts", () => {
    const { container } = render(<AttachedPassage context={context("answered_by", [])} color="#fff" rgb="255,255,255" />);

    expect(container.firstChild).toBeNull();
  });
});
