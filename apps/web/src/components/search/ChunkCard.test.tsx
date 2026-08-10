// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChunkCard } from "./ChunkCard";

const mocks = vi.hoisted(() => ({ submitLabel: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
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
    const persistentContext = screen.getByRole("button", { name: "Open in Context" });
    expect(persistentContext.querySelector("svg")).toBeNull();
    expect(persistentContext.textContent).toContain("Open in");
    expect(persistentContext.textContent).toContain("Context");
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
    expect(contextButtons).toHaveLength(2);
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
