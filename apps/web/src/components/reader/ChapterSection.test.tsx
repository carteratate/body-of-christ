// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import type { ReaderChapter, ReaderPassage } from "@/lib/api";
import { ChapterSection } from "./ChapterSection";
import { historyYear } from "./Passage";

afterEach(cleanup);

function passage(id: string, anchor: string, content: string, extra: Partial<ReaderPassage> = {}): ReaderPassage {
  return { id, anchor, chapter_key: "c", chapter_label: "Canons 290–300", unit_label: null, reference: null, content, ...extra };
}

function chapter(passages: ReaderPassage[], document: Partial<ReaderChapter["document"]> = {}): ReaderChapter {
  return {
    document: {
      id: "d", collection: "canon-law", title: "Code of Canon Law", author: null, year: 1983,
      metadata: null, chunk_count: 3, ...document,
    },
    chapter_key: "c",
    chapter_label: "Canons 290–300",
    passages,
    prev_chapter_key: null,
    next_chapter_key: null,
    highlight_anchor: null,
  };
}

describe("ChapterSection", () => {
  it("test_history_passage_shows_as_earlier_text_under_current", async () => {
    const view = render(
      <ChapterSection
        highlightAnchor={null}
        chapter={chapter([
          passage("p295", "can/295", "Current text of 295."),
          passage("h295", "can/295/history-1983", "Older text of 295.", { superseded_by: "p295" }),
          passage("p296", "can/296", "Current text of 296."),
        ])}
      />,
    );
    const texts = [...view.container.querySelectorAll("p")].map((p) => p.textContent);
    expect(texts.indexOf("Current text of 295.")).toBeLessThan(texts.indexOf("Current text of 296."));
    expect(screen.queryByText("Older text of 295.")).toBeNull();

    const control = screen.getByRole("button", { name: /Earlier text \(1983\)/ });
    // The control sits between 295 and 296, under the passage it was replaced by.
    const order = [...view.container.querySelectorAll("p, button")].map((el) => el.textContent ?? "");
    expect(order.findIndex((t) => t.includes("Earlier text"))).toBeGreaterThan(order.indexOf("Current text of 295."));
    expect(order.findIndex((t) => t.includes("Earlier text"))).toBeLessThan(order.indexOf("Current text of 296."));

    await userEvent.click(control);
    expect(screen.getByText("Older text of 295.")).toBeTruthy();
    expect(screen.getByText("No longer in force")).toBeTruthy();
  });

  it("shows the source credit once, at the end of the section", () => {
    const view = render(
      <ChapterSection
        highlightAnchor={null}
        chapter={chapter([passage("a", "a", "One."), passage("b", "b", "Two.")], {
          facts: { source_credit: "Sourced via CCEL.org" },
        })}
      />,
    );
    expect(screen.getAllByText("Sourced via CCEL.org")).toHaveLength(1);
    const paragraphs = view.container.querySelectorAll("section > p");
    expect(paragraphs[paragraphs.length - 1].textContent).toBe("Sourced via CCEL.org");
  });

  it("shows a passage's quoted author above it and its note after it", () => {
    render(
      <ChapterSection
        highlightAnchor={null}
        chapter={chapter([passage("a", "a", "Blessed are the poor…", { passage_author: "Chrysostom", note: "A passage note." })])}
      />,
    );
    expect(screen.getByText("Chrysostom")).toBeTruthy();
    expect(screen.getByText("A passage note.")).toBeTruthy();
  });

  it("labels a chapter whose work is attributed differently from the document", () => {
    render(
      <ChapterSection
        highlightAnchor={null}
        chapter={chapter([passage("a", "a", "Text.", { work_key: "twelve-topics" })], {
          author: "Gregory Thaumaturgus",
          works: [{ work_key: "twelve-topics", ordinal: 1, title: "Twelve Topics on the Faith", author: "Pseudo-Gregory Thaumaturgus", certainty: "pseudonymous" }],
        })}
      />,
    );
    expect(screen.getByText(/Twelve Topics on the Faith · Pseudo-Gregory Thaumaturgus/)).toBeTruthy();
    expect(screen.getByText("pseudonymous")).toBeTruthy();
  });

  it("renders a chapter without the new fields as before", () => {
    const view = render(<ChapterSection highlightAnchor={null} chapter={chapter([passage("a", "a", "One.")])} />);
    expect(view.container.innerHTML).toBe(
      '<section data-chapter-key="c" class="max-w-[640px] mx-auto px-6 py-6"><h2 class="text-xl font-semibold text-brand-primary mb-4" style="font-family: Georgia, serif;">Canons 290–300</h2><p id="anchor-a" class="text-[length:var(--reader-font-size)] leading-[var(--reader-line-height)] text-brand-primary mb-3" style="font-family: Georgia, serif;">One.</p></section>',
    );
  });

  it("reads the year from a history anchor", () => {
    expect(historyYear("can/700/history-2022")).toBe("2022");
    expect(historyYear("can/700")).toBeNull();
  });
});
