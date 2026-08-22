// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChunkCard } from "./ChunkCard";

const mocks = vi.hoisted(() => ({ submitLabel: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ bookmarkIds: {}, setBookmarkForChunk: vi.fn() }),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  submitLabel: mocks.submitLabel,
}));
vi.mock("@/lib/analytics", () => ({
  trackBookmarkCreated: vi.fn(), trackBookmarkDeleted: vi.fn(),
  trackDocumentOpened: vi.fn(), trackExploreMoreClicked: vi.fn(),
}));

beforeEach(() => mocks.submitLabel.mockResolvedValue({ label_id: "label" }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("ChunkCard feedback", () => {
  it("removes the report prompt when a down label is changed to up", async () => {
    render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: "A passage",
          source: {
            collection: "bible",
            document_title: "Genesis",
            author: null,
            reference: "Genesis 1:1",
            document_id: "00000000-0000-0000-0000-000000000002",
            position: 1,
            anchor: "genesis-1-1",
          },
          reranker_score: 0.9,
          explanation: "Relevant",
        }}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    await userEvent.click(screen.getByRole("button", { name: "Mark as not relevant" }));
    await screen.findByText("Is there a specific problem with this result?", { exact: false });

    await userEvent.click(screen.getByRole("button", { name: "Mark as relevant" }));
    await waitFor(() => expect(screen.queryByText("Is there a specific problem with this result?", { exact: false })).toBeNull());
    expect(mocks.submitLabel).toHaveBeenNthCalledWith(1, "token", expect.any(String), "down", expect.any(String));
    expect(mocks.submitLabel).toHaveBeenNthCalledWith(2, "token", expect.any(String), "up", expect.any(String));
  });

  it("provides themed descriptions for result actions without native title tooltips", async () => {
    render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: "A passage",
          source: {
            collection: "bible",
            document_title: "Genesis",
            author: null,
            reference: "Genesis 1:1",
            document_id: "00000000-0000-0000-0000-000000000002",
            position: 1,
            anchor: "genesis-1-1",
          },
          reranker_score: 0.9,
          explanation: "Relevant",
        }}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );

    const expand = screen.getByRole("button", { name: "Expand result: Bible, Genesis 1:1, 90% relevance" });
    expect(screen.queryByRole("button", { name: "Open in Context" })).toBeNull();
    expect(screen.queryByText("Relevance Score:")).toBeNull();
    expect(screen.getAllByText("90%")).toHaveLength(2);
    expect(expand.getAttribute("aria-describedby")).toBeNull();
    expect(expand.getAttribute("title")).toBeNull();
    expand.focus();
    expect(screen.queryByRole("tooltip")).toBeNull();

    await userEvent.click(expand);
    for (const name of ["Save passage", "Copy passage", "Mark as relevant", "Mark as not relevant", "Query more like this"]) {
      const action = screen.getByRole("button", { name });
      expect(action.getAttribute("aria-describedby")).toBeTruthy();
      expect(action.getAttribute("title")).toBeNull();
    }
    const expectedDescriptions = new Map([
      ["Save passage", "Save Passage"],
      ["Copy passage", "Copy"],
      ["Query more like this", "Start a new search to find passages similar to this one"],
    ]);
    for (const [name, expected] of expectedDescriptions) {
      screen.getByRole("button", { name }).focus();
      expect((await screen.findByRole("tooltip")).textContent).toBe(expected);
      await userEvent.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    }
    const contextButtons = screen.getAllByRole("button", { name: "Open in Context" });
    expect(contextButtons).toHaveLength(1);
    for (const contextButton of contextButtons) {
      contextButton.focus();
      expect((await screen.findByRole("tooltip")).textContent).toBe("Open this passage in the context of the full source");
      await userEvent.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    }
  });

  it("allows expanded actions to wrap on narrow screens", async () => {
    const { container } = render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: "A passage",
          source: {
            collection: "apostolic-exhortations",
            document_title: "Evangelii Gaudium",
            author: "Pope Francis",
            reference: "Evangelii Gaudium 1",
            document_id: "00000000-0000-0000-0000-000000000002",
            position: 1,
            anchor: "evangelii-gaudium-1",
          },
          reranker_score: 0.9,
          explanation: "Relevant",
        }}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { expanded: false }));
    const queryMore = screen.getByRole("button", { name: "Query more like this" });
    expect(queryMore.parentElement?.parentElement?.className).toContain("flex-wrap");
    expect(container.firstElementChild?.className).toContain("overflow-hidden");
    const header = container.querySelector(".h-\\[96px\\]");
    expect(header?.className).toContain("sm:h-[68px]");
    expect(screen.getAllByText("Apostolic Exhortations")[0].className).toContain("max-w-[10rem]");
    expect(screen.getAllByText("Evangelii Gaudium 1")[0].className).toContain("line-clamp-2");
  });

  it("uses a compact source-aware Summa citation in the stacked mobile hierarchy", () => {
    render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: "A passage",
          source: {
            collection: "summa",
            document_title: "Summa Theologiae",
            author: "Thomas Aquinas",
            reference: "Summa Theologiae, First Part, Question 22 - The Providence of God (FOUR ARTICLES), Article 2 - Whether everything is subject to the providence of God?",
            document_id: "00000000-0000-0000-0000-000000000002",
            position: 1,
            anchor: "summa-1-22-2",
          },
          reranker_score: 0.87,
          explanation: "Relevant",
        }}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );

    expect(screen.getByText("First Part · Q. 22 · Art. 2").className).toContain("line-clamp-2");
    const authorLabels = screen.getAllByText("Thomas Aquinas");
    expect(authorLabels).toHaveLength(2);
    expect(authorLabels.every((label) => label.className.includes("truncate"))).toBe(true);
  });

  it("does not present the Catholic Church as a card author", () => {
    render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: "A passage",
          source: {
            collection: "catechism",
            document_title: "Catechism of the Catholic Church",
            author: "Catholic Church",
            reference: "CCC §1",
            document_id: "00000000-0000-0000-0000-000000000002",
            position: 1,
            anchor: "ccc-1",
          },
          reranker_score: 0.9,
          explanation: "Relevant",
        }}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );

    expect(screen.queryByText("Catholic Church")).toBeNull();
    expect(screen.getByRole("button", { expanded: false }).getAttribute("aria-label")).not.toContain("Catholic Church");
  });
});


describe("ChunkCard attached passage placement", () => {
  function summaResult(context: unknown, content: string) {
    return {
      chunk_id: "00000000-0000-0000-0000-000000000001",
      content,
      source: {
        collection: "summa",
        document_title: "Summa Theologiae",
        author: "Thomas Aquinas",
        reference: "ST I, Question 1, Article 1",
        document_id: "00000000-0000-0000-0000-000000000002",
        position: 1,
        anchor: "summa-q1-a1",
      },
      reranker_score: 0.9,
      explanation: "Relevant",
      context,
    };
  }

  async function expand(result: unknown) {
    const { container } = render(
      <ChunkCard
        result={result as never}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    return Array.from(container.querySelectorAll("p")).map((p) => p.textContent);
  }

  /** Whether an attachment region is present at all — the heading is a span, so a
   *  <p>-only scan can never see it, and a negative assertion over `expand()` would
   *  hold even for a card that renders the attachment on every result. */
  function hasAttachment(): boolean {
    return screen.queryByRole("complementary") !== null;
  }

  it("puts Aquinas's answer BELOW a matched objection", async () => {
    // The objection is the passage that matched and states a position he refutes, so it
    // must lead. Reversing this would present his answer as the result.
    const text = await expand(summaResult(
      { relation: "answered_by", parts: [{ content: "THE ANSWER", reference: null, unit_label: "I answer that", anchor: "a/1" }] },
      "THE OBJECTION",
    ));

    // Presence asserted before order: indexOf returns -1 when absent, and -1 is less
    // than every valid index, so an ordering check ALONE passes when the attachment is
    // not rendered at all.
    expect(text).toContain("THE OBJECTION");
    expect(text).toContain("THE ANSWER");
    expect(text.indexOf("THE OBJECTION")).toBeLessThan(text.indexOf("THE ANSWER"));
  });

  it("puts the objection ABOVE a matched reply", async () => {
    // A reply opens mid-thought — "The Philosopher is speaking of those who..." means
    // nothing until you know what the Philosopher said. So on a reply card the matched
    // passage is deliberately second.
    const text = await expand(summaResult(
      { relation: "answers", parts: [{ content: "THE OBJECTION", reference: null, unit_label: "Objection 1", anchor: "a/0" }] },
      "THE REPLY",
    ));

    expect(text).toContain("THE OBJECTION");
    expect(text).toContain("THE REPLY");
    expect(text.indexOf("THE OBJECTION")).toBeLessThan(text.indexOf("THE REPLY"));
  });

  it("places from relation alone, not from the attached passage's label", async () => {
    // A label-sniffing heuristic agrees with `relation` on the common shapes and fails
    // exactly here: an unlabelled objection would land BELOW the reply while the
    // boundary above still reads "answered below", pointing at nothing.
    const text = await expand(summaResult(
      { relation: "answers", parts: [{ content: "THE OBJECTION", reference: null, unit_label: null, anchor: "a/0" }] },
      "THE REPLY",
    ));

    expect(text).toContain("THE OBJECTION");
    expect(text.indexOf("THE OBJECTION")).toBeLessThan(text.indexOf("THE REPLY"));
  });

  it("shows nothing extra for a result that needs no attachment", async () => {
    await expand(summaResult(null, "I answer that, the passage stands alone."));

    expect(hasAttachment()).toBe(false);
  });

  it("the no-attachment check can actually fail", async () => {
    // Guards the guard: `expand()` collects only <p>, and the boundary heading is a
    // <span>, so a negative assertion phrased over that text would be unfalsifiable.
    await expand(summaResult(
      { relation: "answered_by", parts: [{ content: "THE ANSWER", reference: null, unit_label: "I answer that", anchor: "a/1" }] },
      "THE OBJECTION",
    ));

    expect(hasAttachment()).toBe(true);
  });
});

describe("ChunkCard keeps the attachment out of every action", () => {
  // The attachment is presentation. Everything the user DOES with a card must address
  // the passage they actually matched — it is what was ranked, persisted and cited.
  function summaObjection() {
    return {
      chunk_id: "00000000-0000-0000-0000-000000000001",
      content: "THE MATCHED OBJECTION",
      source: {
        collection: "summa",
        document_title: "Summa Theologiae",
        author: "Thomas Aquinas",
        reference: "ST I, Question 2, Article 3",
        document_id: "00000000-0000-0000-0000-000000000002",
        position: 1,
        anchor: "summa-q2-a3",
        unit_label: "Objection 1",
      },
      reranker_score: 0.9,
      explanation: "Relevant",
      context: {
        relation: "answered_by",
        parts: [{ content: "THE ATTACHED ANSWER", reference: null, unit_label: "I answer that", anchor: "a/1" }],
      },
    };
  }

  async function renderExpanded(onExploreMore = vi.fn()) {
    render(
      <ChunkCard
        result={summaObjection() as never}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={onExploreMore}
      />,
    );
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    return onExploreMore;
  }

  it("copies the matched passage only, and names its role in the citation", async () => {
    // Ingest strips "Objection N" out of `content`, so a copied objection is a bare
    // heterodox proposition cited to the Summa. The clipboard is where this text leaves
    // the app entirely — nothing downstream can mark it.
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    await renderExpanded();
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));

    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("THE MATCHED OBJECTION");
    expect(copied).not.toContain("THE ATTACHED ANSWER");
    expect(copied).toContain("Objection 1");
  });

  it("seeds Explore More from the matched passage, not the attachment", async () => {
    const onExploreMore = await renderExpanded();
    await userEvent.click(screen.getByRole("button", { name: "Query more like this" }));

    expect(onExploreMore.mock.calls[0][0]).toContain("THE MATCHED OBJECTION");
    expect(onExploreMore.mock.calls[0][0]).not.toContain("THE ATTACHED ANSWER");
  });

  it("keeps the role marker out of any truncating element", () => {
    // A Summa reference averages 214 characters and overflows the desktop column, so a
    // marker appended INSIDE the truncated citation is ellipsed away before it paints —
    // silently, on 97% of objection cards, on the one surface the marker exists for.
    // jsdom has no layout, so this asserts the structural property instead: the tag is
    // never a descendant of a `truncate` or `line-clamp` element.
    const { container } = render(
      <ChunkCard
        result={summaObjection() as never}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );

    const tags = Array.from(container.querySelectorAll("span"))
      .filter((el) => el.textContent?.includes("Objection 1") && el.children.length === 0);
    expect(tags.length).toBeGreaterThan(0);
    for (const tag of tags) {
      expect(tag.closest(".truncate")).toBeNull();
      expect(tag.closest("[class*='line-clamp']")).toBeNull();
    }
  });

  it("names the passage's role on the collapsed card", async () => {
    // The collapsed card is the DEFAULT state and shows only a citation. Without the
    // role, an objection is indistinguishable from Aquinas's own teaching until opened.
    render(
      <ChunkCard
        result={summaObjection() as never}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );

    expect(screen.getAllByText(/Objection 1/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { expanded: false }).getAttribute("aria-label"))
      .toContain("Objection 1");
  });
});
