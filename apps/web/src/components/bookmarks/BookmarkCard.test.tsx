// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BookmarkCard } from "./BookmarkCard";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/analytics", () => ({
  trackBookmarkDeleted: vi.fn(),
  trackDocumentOpened: vi.fn(),
  trackExploreMoreClicked: vi.fn(),
}));

afterEach(cleanup);

describe("BookmarkCard action descriptions", () => {
  it("uses themed descriptions rather than native title tooltips", async () => {
    render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: null,
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "catechism",
              document_title: "Catechism of the Catholic Church",
              author: null,
              reference: "CCC §1000",
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: "ccc-1000",
              chapter_key: "ccc-1000-1099",
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={vi.fn()}
        showToast={vi.fn()}
      />,
    );

    const expectedDescriptions = new Map([
      ["Open passage in context", "Open this passage in the context of the full source"],
      ["Remove bookmark", "Remove this passage from Saved Passages."],
      ["Copy passage", "Copy"],
      ["Query more like this", "Start a new search to find passages similar to this one"],
    ]);
    for (const [name, expected] of expectedDescriptions) {
      const action = screen.getByRole("button", { name });
      const descriptionId = action.getAttribute("aria-describedby");
      expect(descriptionId).toBeTruthy();
      expect(action.getAttribute("title")).toBeNull();
      action.focus();
      expect((await screen.findByRole("tooltip")).textContent).toBe(expected);
      await userEvent.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    }
  });
});
