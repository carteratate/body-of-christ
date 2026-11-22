// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChunkCard } from "./ChunkCard";
import { navigations } from "@/test/next-link-mock";
import { hasReaderReturnMarker } from "@/lib/readerNavigation";
import { trackDocumentOpened } from "@/lib/analytics";

const mocks = vi.hoisted(() => ({ submitLabel: vi.fn(), prefetch: vi.fn() }));
vi.mock("next/link", () => import("@/test/next-link-mock"));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), prefetch: mocks.prefetch }),
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
  trackDocumentOpened: vi.fn(),
}));

beforeEach(() => mocks.submitLabel.mockResolvedValue({ label_id: "label" }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
  navigations.length = 0;
  sessionStorage.clear();
});

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
      />,
    );

    const expand = screen.getByRole("button", { name: "Expand result: Bible, Genesis 1:1, 90% relevance" });
    expect(screen.queryByRole("link", { name: "Open in Context" })).toBeNull();
    expect(screen.queryByText("Relevance Score:")).toBeNull();
    expect(screen.getAllByText("90%")).toHaveLength(2);
    expect(expand.getAttribute("aria-describedby")).toBeNull();
    expect(expand.getAttribute("title")).toBeNull();
    expand.focus();
    expect(screen.queryByRole("tooltip")).toBeNull();

    await userEvent.click(expand);
    for (const name of ["Save passage", "Copy passage", "Mark as relevant", "Mark as not relevant"]) {
      const action = screen.getByRole("button", { name });
      expect(action.getAttribute("aria-describedby")).toBeTruthy();
      expect(action.getAttribute("title")).toBeNull();
    }
    const expectedDescriptions = new Map([
      ["Save passage", "Save Passage"],
      ["Copy passage", "Copy"],
      ["Mark as relevant", "Tell TheoCorpus this result helped answer your question."],
      ["Mark as not relevant", "Tell TheoCorpus this result was not useful."],
    ]);
    for (const [name, expected] of expectedDescriptions) {
      screen.getByRole("button", { name }).focus();
      expect((await screen.findByRole("tooltip")).textContent).toBe(expected);
      await userEvent.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    }
    const contextLinks = screen.getAllByRole("link", { name: "Open in Context" });
    expect(contextLinks).toHaveLength(1);
    expect(contextLinks[0].getAttribute("aria-describedby")).toBeNull();
    contextLinks[0].focus();
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("shows the guest open-in-context guidance above the Open in Context button", async () => {
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
        searchId={null}
        token=""
        isGuest
        showOpenContextHint
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Expand result: Bible, Genesis 1:1, 90% relevance" }));
    expect(screen.getByRole("status").textContent).toContain("Open the passage in context to read the surrounding text.");
    expect(screen.getByRole("link", { name: "Open in Context" })).toBeTruthy();
  });

  it("allows expanded actions to wrap on narrow screens", async () => {
    const { container } = render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: "A passage",
          source: {
            collection: "theologians",
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
      />,
    );

    await userEvent.click(screen.getByRole("button", { expanded: false }));
    const openContext = screen.getByRole("link", { name: "Open in Context" });
    expect(openContext.parentElement?.parentElement?.parentElement?.className).toContain("flex-wrap");
    expect(screen.queryByRole("button", { name: "Query more like this" })).toBeNull();
    expect(container.firstElementChild?.className).toContain("overflow-hidden");
    const header = container.querySelector(".h-\\[96px\\]");
    expect(header?.className).toContain("sm:h-[68px]");
    expect(screen.getAllByText("Theology & Spirituality")[0].className).toContain("max-w-[10rem]");
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

  async function renderExpanded() {
    render(
      <ChunkCard
        result={summaObjection() as never}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
      />,
    );
    await userEvent.click(screen.getByRole("button", { expanded: false }));
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

  it("names the passage's role above the opened text, not on the collapsed card", async () => {
    // The collapsed card shows no passage text, so there is nothing to misread there;
    // the role is named where the text is (Carter, 12 Nov 2026). Screen readers still
    // hear it in the header's name.
    render(
      <ChunkCard
        result={summaObjection() as never}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
      />,
    );
    const header = screen.getByRole("button", { expanded: false });
    expect(header.textContent).not.toContain("Objection 1");
    expect(header.getAttribute("aria-label")).toContain("Objection 1");

    await userEvent.click(header);
    const caption = screen.getByText("Objection 1");
    expect(caption.className).toContain("text-brand-muted");
    expect(caption.compareDocumentPosition(screen.getByText("THE MATCHED OBJECTION"))
      & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("ChunkCard role caption when the text already says it", () => {
  function summaAnswer(content: string) {
    return {
      chunk_id: "00000000-0000-0000-0000-000000000001",
      content,
      source: {
        collection: "summa",
        document_title: "Summa Theologiae",
        author: "Thomas Aquinas",
        reference: "ST III, Question 73, Article 5",
        document_id: "00000000-0000-0000-0000-000000000002",
        position: 1,
        anchor: "summa-q73-a5",
        unit_label: "I answer that",
      },
      reranker_score: 0.9,
      explanation: "Relevant",
    };
  }

  async function open(content: string) {
    render(
      <ChunkCard
        result={summaAnswer(content) as never}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
      />,
    );
    const header = screen.getByRole("button", { expanded: false });
    await userEvent.click(header);
    return header;
  }

  it("leaves the caption off when the passage opens with its own role", async () => {
    const header = await open("I answer that, This sacrament was appropriately instituted.");
    expect(screen.queryByText("I answer that", { exact: true })).toBeNull();
    // Screen readers still hear the role in the header's name.
    expect(header.getAttribute("aria-label")).toContain("I answer that");
  });

  it("keeps the caption on an answer that continues from an earlier passage", async () => {
    await open("A falling short of the just due may be considered in respect of the thing.");
    expect(screen.getByText("I answer that", { exact: true })).toBeTruthy();
  });
});

const RESULT = {
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
};

async function openContextLink(props: Partial<React.ComponentProps<typeof ChunkCard>> = {}) {
  const view = render(<ChunkCard result={RESULT} index={0} searchId="00000000-0000-0000-0000-000000000003" token="token" {...props} />);
  await userEvent.click(screen.getByRole("button", { expanded: false }));
  return { ...view, link: screen.getByRole("link", { name: "Open in Context" }) as HTMLAnchorElement };
}

function returnKeyOf(link: HTMLAnchorElement): string | null {
  return new URL(link.href).searchParams.get("returnKey");
}

describe("ChunkCard Open in Context link", () => {
  it("moves to a fresh key after a same-tab open, so a marked key is never linked again", async () => {
    const { link } = await openContextLink();
    const first = returnKeyOf(link);
    await userEvent.click(link);
    expect(hasReaderReturnMarker(first, "search")).toBe(true);

    await waitFor(() => expect(returnKeyOf(screen.getByRole("link", { name: "Open in Context" }) as HTMLAnchorElement)).not.toBe(first));
    const second = returnKeyOf(screen.getByRole("link", { name: "Open in Context" }) as HTMLAnchorElement);
    expect(second).toMatch(/^[0-9a-f-]{36}$/);
    expect(second).not.toBe(first);
    // A cmd-click now opens a key with no marker, even if the new tab copies this tab's storage.
    expect(hasReaderReturnMarker(second, "search")).toBe(false);
  });

  it("renders a stable reader href, so the URL a hover warmed is the one opened", async () => {
    const { link, rerender } = await openContextLink();
    const href = link.getAttribute("href")!;
    expect(href).toMatch(/^\/reader\/00000000-0000-0000-0000-000000000002\?from=search&returnKey=[0-9a-f-]{36}&anchor=genesis-1-1$/);
    rerender(<ChunkCard result={RESULT} index={0} searchId="00000000-0000-0000-0000-000000000003" token="token" />);
    expect(screen.getByRole("link", { name: "Open in Context" }).getAttribute("href")).toBe(href);

    await userEvent.click(link);
    expect(navigations).toEqual([href]);
  });

  it("writes the return marker and tracks the open for a same-tab click", async () => {
    const { link } = await openContextLink();
    const key = returnKeyOf(link);
    expect(hasReaderReturnMarker(key, "search")).toBe(false);

    await userEvent.click(link);
    expect(hasReaderReturnMarker(key, "search")).toBe(true);
    expect(trackDocumentOpened).toHaveBeenCalledWith({ documentId: RESULT.source.document_id, collection: "bible", source: "chunk_card" });
  });

  it("leaves a cmd/ctrl-click to the browser without a return marker", async () => {
    const { link } = await openContextLink();
    for (const modifier of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }]) {
      const event = new MouseEvent("click", { bubbles: true, cancelable: true, ...modifier });
      link.dispatchEvent(event);
      expect(event.defaultPrevented).toBe(false);
    }
    expect(navigations).toEqual([]);
    expect(hasReaderReturnMarker(returnKeyOf(link), "search")).toBe(false);
    // The open still counts.
    expect(trackDocumentOpened).toHaveBeenCalledTimes(3);
  });

  it("sends a guest to the guest reader with the back guide while the hint shows", async () => {
    const onDismissOpenContextHint = vi.fn();
    const { link } = await openContextLink({ isGuest: true, searchId: null, token: "", showOpenContextHint: true, onDismissOpenContextHint });
    expect(link.getAttribute("href")).toMatch(/^\/reader\/guest\/00000000-0000-0000-0000-000000000002\?from=search&returnKey=[0-9a-f-]{36}&anchor=genesis-1-1&guideBack=1$/);
    const href = link.getAttribute("href");
    await userEvent.click(link);
    expect(onDismissOpenContextHint).toHaveBeenCalledTimes(1);
    expect(navigations).toEqual([href]);
  });

  it("does not prefetch on sight, and prefetches its exact href once the pointer rests on it", async () => {
    const { link } = await openContextLink();
    expect(link.dataset.prefetch).toBe("false");
    vi.useFakeTimers();
    fireEvent.pointerEnter(link, { pointerType: "mouse" });
    vi.advanceTimersByTime(100);
    expect(mocks.prefetch).not.toHaveBeenCalled();
    vi.advanceTimersByTime(50);
    expect(mocks.prefetch).toHaveBeenCalledExactlyOnceWith(link.getAttribute("href"));
  });
});

describe("ChunkCard relevance explanation", () => {
  const SHOW = "Show why this is relevant (AI generated)";
  const SHOWN = "Why this is relevant (AI generated)";

  function renderCard(explanation: string | null) {
    const view = render(<ChunkCard result={{ ...RESULT, explanation }} index={0} searchId={null} token="token" />);
    return {
      ...view,
      rerenderWith: (next: string | null) =>
        view.rerender(<ChunkCard result={{ ...RESULT, explanation: next }} index={0} searchId={null} token="token" />),
    };
  }

  async function expandCard() {
    await userEvent.click(screen.getByRole("button", { name: /^Expand result/ }));
  }

  it("starts closed when the card expands: passage and header show, explanation text does not", async () => {
    renderCard("Because it names the Incarnation");
    await expandCard();

    expect(screen.getByText("A passage")).toBeTruthy();
    const header = screen.getByRole("button", { name: SHOW });
    expect(header.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Because it names the Incarnation")).toBeNull();
  });

  it("opens and closes from its header, dropping 'Show' while open", async () => {
    renderCard("Because it names the Incarnation");
    await expandCard();

    await userEvent.click(screen.getByRole("button", { name: SHOW }));
    const header = screen.getByRole("button", { name: SHOWN });
    expect(header.getAttribute("aria-expanded")).toBe("true");
    const text = screen.getByText("Because it names the Incarnation");
    expect(header.getAttribute("aria-controls")).toBe(text.parentElement!.id);

    await userEvent.click(header);
    expect(screen.getByRole("button", { name: SHOW }).getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Because it names the Incarnation")).toBeNull();
  });

  it("shows the skeleton while streaming, then the text replaces it without another click", async () => {
    const { rerenderWith } = renderCard(null);
    await expandCard();
    await userEvent.click(screen.getByRole("button", { name: SHOW }));
    expect(screen.getByTestId("explanation-skeleton")).toBeTruthy();

    rerenderWith("Because it names");
    expect(screen.queryByTestId("explanation-skeleton")).toBeNull();
    expect(screen.getByText("Because it names")).toBeTruthy();

    rerenderWith("Because it names the Incarnation");
    expect(screen.getByText("Because it names the Incarnation")).toBeTruthy();
  });

  it("starts closed again after the card is collapsed and re-expanded", async () => {
    renderCard("Because it names the Incarnation");
    await expandCard();
    await userEvent.click(screen.getByRole("button", { name: SHOW }));
    await userEvent.click(screen.getByRole("button", { name: /^Collapse result/ }));
    await expandCard();

    expect(screen.getByRole("button", { name: SHOW })).toBeTruthy();
    expect(screen.queryByText("Because it names the Incarnation")).toBeNull();
  });

  it("renders no header when there is no explanation", async () => {
    renderCard("");
    await expandCard();

    expect(screen.queryByRole("button", { name: SHOW })).toBeNull();
    expect(screen.queryByText(/why this is relevant/i)).toBeNull();
  });
});

describe("ChunkCard excerpt-only documents (issue #265)", () => {
  function renderCard(extra: Record<string, unknown>) {
    render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: "Liberty, the highest of natural endowments",
          source: {
            collection: "encyclicals",
            document_title: "Libertas",
            author: "Pope Leo XIII",
            reference: "Libertas 1",
            document_id: "00000000-0000-0000-0000-000000000002",
            position: 1,
            anchor: "libertas-1",
            ...extra,
          },
          reranker_score: 0.9,
          explanation: "Relevant",
        }}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
      />,
    );
  }

  it("shows the passage and swaps Open in Context for the source link", async () => {
    renderCard({ reader_access: "excerpt", source_url: "https://www.papalencyclicals.net/leo13/l13liber.htm" });
    await userEvent.click(screen.getByRole("button", { expanded: false }));

    expect(screen.getAllByText(/Liberty, the highest of natural endowments/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Open in Context" })).toBeNull();
    const link = screen.getByRole("link", { name: /Read the full text at the source/ });
    expect(link.getAttribute("href")).toBe("https://www.papalencyclicals.net/leo13/l13liber.htm");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("offers neither link when an excerpt-only document has no known source", async () => {
    renderCard({ reader_access: "excerpt", source_url: null });
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.queryByRole("link", { name: "Open in Context" })).toBeNull();
    expect(screen.queryByRole("link", { name: /Read the full text/ })).toBeNull();
  });

  it("shows the rights holder's credit right after the passage", async () => {
    renderCard({
      reader_access: "excerpt",
      source_url: "https://www.vatican.va/content/leo-xiii/en/encyclicals/documents/hf_l-xiii_enc_20061888_libertas.html",
      source_credit: "© Dicastery for Communication – Libreria Editrice Vaticana",
    });
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByText("© Dicastery for Communication – Libreria Editrice Vaticana")).toBeTruthy();
  });

  it("copies the credit with an excerpt passage", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderCard({
      reader_access: "excerpt",
      source_url: "https://www.vatican.va/x.html",
      source_credit: "© Dicastery for Communication – Libreria Editrice Vaticana",
    });
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));
    const copied = writeText.mock.calls[0][0] as string;
    expect(copied).toContain("Liberty, the highest of natural endowments");
    expect(copied.endsWith("© Dicastery for Communication – Libreria Editrice Vaticana")).toBe(true);
  });

  it("shows no credit for a full document, even if one is sent", async () => {
    renderCard({ reader_access: "full", source_url: null, source_credit: "should not show" });
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.queryByText("should not show")).toBeNull();
  });

  it("keeps Open in Context for a full document", async () => {
    renderCard({ reader_access: "full", source_url: null });
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByRole("link", { name: "Open in Context" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Read the full text/ })).toBeNull();
  });
});

describe("ChunkCard footnotes (issue #279)", () => {
  const CONTENT = "The death penalty is inadmissible.";
  const CREDIT = "Excerpts from the English translation of the Catechism of the Catholic Church";

  async function renderCatechism(footnotes: unknown) {
    render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: CONTENT,
          source: {
            collection: "catechism",
            document_title: "Catechism of the Catholic Church",
            author: "Catholic Church",
            reference: "CCC 2267",
            document_id: "00000000-0000-0000-0000-000000000002",
            position: 1,
            reader_access: "excerpt",
            source_url: "https://www.usccb.org/sites/default/files/flipbooks/catechism/index.html",
            source_credit: CREDIT,
          },
          reranker_score: 0.9,
          explanation: null,
          footnotes: footnotes as never,
        }}
        index={0}
        searchId={null}
        token="token"
      />,
    );
    await userEvent.click(screen.getByRole("button", { expanded: false }));
  }

  it("puts each marker at its offset and lists the notes under the passage", async () => {
    await renderCatechism([
      { n: 67, text: "First note.", at: 3 },
      { n: 68, text: "Francis, Address.", at: CONTENT.length },
    ]);

    const passage = screen.getByText(/death penalty/).closest("p")!;
    const markers = [...passage.querySelectorAll("sup")].map((sup) => sup.textContent);
    expect(markers).toEqual(["67", "68"]);
    expect(passage.textContent).toBe(`The67${CONTENT.slice(3)}68`);
    expect(screen.getByText("68. Francis, Address.")).toBeTruthy();
  });

  it("ignores a note whose offset is outside the passage", async () => {
    await renderCatechism([{ n: 70, text: "Nowhere.", at: CONTENT.length + 5 }]);

    expect(screen.getByText(CONTENT).querySelector("sup")).toBeNull();
    expect(screen.queryByText("70. Nowhere.")).toBeNull();
    expect(screen.queryByText("Notes")).toBeNull();
  });

  it("copies the text, then its notes, then the credit", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    await renderCatechism([{ n: 68, text: "Francis, Address.", at: CONTENT.length }]);
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));

    const copied = writeText.mock.calls[0][0] as string;
    expect(copied.startsWith(`${CONTENT}⁶⁸ — `)).toBe(true);
    const notes = copied.indexOf("Notes:\n68. Francis, Address.");
    expect(notes).toBeGreaterThan(0);
    expect(copied.indexOf(CREDIT)).toBeGreaterThan(notes);
    expect(copied.endsWith(CREDIT)).toBe(true);
  });
});

describe("ChunkCard rejected voice (corpus cleanup 2.4d)", () => {
  const LABEL = "Condemned proposition 31 (condemned by Leo X, Exsurge Domine)";
  const TEXT = "In every good work the just man sins.";

  function condemned(source: Record<string, unknown> = {}) {
    return {
      chunk_id: "00000000-0000-0000-0000-000000000031",
      content: TEXT,
      source: {
        collection: "papal-documents",
        document_title: "Exsurge Domine",
        author: "Pope Leo X",
        reference: "Pope Leo X — Exsurge Domine, §31",
        document_id: "00000000-0000-0000-0000-000000000002",
        position: 31,
        anchor: "exsurge-domine/31",
        unit_label: LABEL,
        voice: "rejected",
        ...source,
      },
      reranker_score: 0.81,
      explanation: "Leo X condemned this proposition.",
    };
  }

  function renderResult(result: ReturnType<typeof condemned>) {
    return render(
      <ChunkCard result={result as never} index={0} searchId="00000000-0000-0000-0000-000000000003" token="token" />,
    );
  }

  it("keeps the collapsed header as it was: no label", () => {
    // Carter, 12 Nov 2026: the header shows the author and the reference only.
    renderResult(condemned());
    const header = screen.getByRole("button", { expanded: false });
    expect(header.textContent).not.toContain(LABEL);
    expect(screen.queryByText(LABEL)).toBeNull();
  });

  it("sets the opened text off as a quotation under a caption naming whose it is", async () => {
    renderResult(condemned());
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    const caption = screen.getByText(LABEL).closest("p")!;
    expect(caption.textContent).toBe(`${LABEL} · a position the document rejects`);
    expect(caption.className).toContain("text-brand-muted");
    const quoted = screen.getByText(TEXT).closest("[data-voice='rejected']")!;
    expect(quoted.className).toContain("border-l-2");
    expect(quoted.className).toContain("italic");
    expect(caption.compareDocumentPosition(quoted) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("adds the label to the copied citation in brackets", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderResult(condemned());
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));
    expect(writeText.mock.calls[0][0]).toBe(
      `${TEXT} — Pope Leo X — Exsurge Domine, §31 [${LABEL}] (Papal documents)`,
    );
  });

  it("names a rejected Summa objection once, in its caption", async () => {
    renderResult(condemned({
      collection: "summa", document_title: "Summa Theologiae", author: "Thomas Aquinas",
      reference: "Summa Theologiae I-II, q. 109, a. 2", unit_label: "Objection 1",
    }));
    const header = screen.getByRole("button", { expanded: false });
    expect(header.textContent).not.toContain("Objection 1");
    await userEvent.click(header);
    expect(screen.getAllByText("Objection 1")).toHaveLength(1);
    expect(screen.getByText("Objection 1").closest("p")!.textContent)
      .toBe("Objection 1 · a position the document rejects");
  });

  it("renders exactly as today without the field", async () => {
    // Recorded from master's ChunkCard, before 2.4d. An unknown voice is no voice.
    for (const voice of [undefined, "affirmed"]) {
      vi.spyOn(crypto, "randomUUID").mockReturnValue("11111111-1111-4111-8111-111111111111");
      const { container, unmount } = renderResult(condemned({ voice }));
      const html = () => container.innerHTML.replace(/_r_[0-9a-z]+_|«r[0-9a-z]+»|:r[0-9a-z]+:/g, "«id»");
      expect(html()).toMatchSnapshot("collapsed");
      await userEvent.click(screen.getByRole("button", { expanded: false }));
      expect(html()).toMatchSnapshot("opened");
      unmount();
    }
  });
});

describe("ChunkCard text labels (corpus cleanup 2.4f)", () => {
  const LATIN = "https://www.vatican.va/content/francesco/la/motu_proprio/documents/papa-francesco-motu-proprio_20150815_de-concordia-inter-codices.html";
  const ORE = "Unofficial English translation (L’Osservatore Romano). The Latin text is official.";

  function canon(source: Record<string, unknown> = {}) {
    return {
      chunk_id: "00000000-0000-0000-0000-000000001108",
      content: "Only those marriages are valid which are contracted before the local ordinary…",
      source: {
        collection: "canon-law",
        document_title: "Code of Canon Law",
        author: null,
        reference: "Can. 1108",
        document_id: "00000000-0000-0000-0000-000000000002",
        position: 1108,
        anchor: "can/1108",
        facts: { source_credit: "© Libreria Editrice Vaticana" },
        text_status: "unofficial_english",
        official_latin_url: LATIN,
        ...source,
      },
      reranker_score: 0.81,
      explanation: "Relevant",
    };
  }

  function renderResult(result: ReturnType<typeof canon>) {
    return render(
      <ChunkCard result={result as never} index={0} searchId="00000000-0000-0000-0000-000000000003" token="token" />,
    );
  }

  it("shows neither label on the collapsed card", () => {
    renderResult(canon());
    renderResult(canon({ text_status: null, official_latin_url: null, text_source: "ocr" }));
    expect(screen.queryByText(/Unofficial English/)).toBeNull();
    expect(screen.queryByText("Text from a scanned edition")).toBeNull();
  });

  it("shows the unofficial-English line with the Latin linked, before the credit", async () => {
    renderResult(canon());
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    const lines = [...screen.getByTestId("passage-facts").querySelectorAll("p")].map((p) => p.textContent);
    // The link's screen-reader note sits inside the sentence.
    expect(lines).toEqual([
      "Unofficial English translation (L’Osservatore Romano). The Latin text is official (opens in a new tab).",
      "© Libreria Editrice Vaticana",
    ]);
    const link = screen.getByRole("link", { name: /The Latin text is official/ });
    expect(link.getAttribute("href")).toBe(LATIN);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("shows the scanned-edition label when the passage is opened", async () => {
    renderResult(canon({ collection: "church-fathers", text_status: null, official_latin_url: null, text_source: "ocr", facts: null }));
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByTestId("text-label").textContent).toBe("Text from a scanned edition");
  });

  it("keeps the sentence without a link when the Latin's address is missing", async () => {
    renderResult(canon({ official_latin_url: null }));
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByTestId("text-label").textContent).toBe(ORE);
    expect(screen.queryByRole("link", { name: /The Latin text is official/ })).toBeNull();
  });
});
