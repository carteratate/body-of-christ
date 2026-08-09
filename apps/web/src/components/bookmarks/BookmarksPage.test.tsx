// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Bookmark } from "@/lib/api";
import { BookmarksPage } from "./BookmarksPage";

const state = vi.hoisted(() => ({
  token: "token",
  getBookmarks: vi.fn(),
  removeBookmark: vi.fn(),
  setBookmarkForChunk: vi.fn(),
  showToast: vi.fn(),
}));

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ token: state.token, setBookmarkForChunk: state.setBookmarkForChunk }),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  getBookmarks: state.getBookmarks,
  removeBookmark: state.removeBookmark,
}));
vi.mock("./BookmarkCard", () => ({
  BookmarkCard: ({ bookmark, onRemove }: { bookmark: Bookmark; onRemove: (bookmark: Bookmark) => void }) => (
    <div data-testid="bookmark-card">
      <span>{bookmark.id}</span>
      <button type="button" onClick={() => onRemove(bookmark)}>Remove {bookmark.id}</button>
    </div>
  ),
}));
vi.mock("@/components/common", () => ({
  Toast: () => null,
  useToast: () => ({ toast: { visible: false, message: "", type: "success" }, showToast: state.showToast, dismissToast: vi.fn() }),
}));

function bookmark(id: string, content: string, overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id,
    chunk_id: `chunk-${id}`,
    created_at: `2026-08-0${4 - Number(id)}T12:00:00Z`,
    note: null,
    chunk: {
      content,
      source: {
        collection: "bible",
        document_title: "Genesis",
        author: null,
        reference: `Genesis ${id}:1`,
        document_id: "doc-1",
        anchor: null,
        chapter_key: "genesis-1",
      },
    },
    ...overrides,
  };
}

beforeEach(() => {
  state.token = "token";
  state.getBookmarks.mockReset();
  state.removeBookmark.mockReset();
  state.removeBookmark.mockResolvedValue(undefined);
  state.setBookmarkForChunk.mockReset();
  state.showToast.mockReset();
  state.getBookmarks.mockResolvedValue([
    bookmark("1", "Newest passage about grace"),
    bookmark("2", "Middle passage", { note: "A private mercy reflection" }),
    bookmark("3", "Oldest passage about grace"),
  ]);
});

afterEach(cleanup);

describe("BookmarksPage search", () => {
  it("filters locally without changing newest-first order", async () => {
    render(<BookmarksPage />);
    expect((await screen.findAllByTestId("bookmark-card")).map((item) => item.firstChild?.textContent)).toEqual(["1", "2", "3"]);

    await userEvent.type(screen.getByRole("searchbox", { name: "Search saved passages" }), "grace");

    expect(screen.getAllByTestId("bookmark-card").map((item) => item.firstChild?.textContent)).toEqual(["1", "3"]);
  });

  it("searches personal notes and offers a clear no-match state", async () => {
    render(<BookmarksPage />);
    const search = await screen.findByRole("searchbox", { name: "Search saved passages" });

    await userEvent.type(search, "mercy reflection");
    expect(screen.getByTestId("bookmark-card").firstChild?.textContent).toBe("2");

    await userEvent.clear(search);
    await userEvent.type(search, "not present anywhere");
    expect(screen.getByText("No saved passages match that search.")).toBeTruthy();
    expect(screen.queryByTestId("bookmark-card")).toBeNull();
  });

  it("matches collection labels, source metadata, and accent-insensitive text", async () => {
    state.getBookmarks.mockResolvedValue([
      bookmark("1", "A passage by Thérèse", {
        chunk: {
          content: "A passage by Thérèse",
          source: {
            collection: "church-fathers",
            document_title: "The Interior Castle",
            author: "Teresa of Ávila",
            reference: "Dwelling One",
            document_id: "doc-1",
            anchor: null,
            chapter_key: "one",
          },
        },
      }),
    ]);
    render(<BookmarksPage />);
    const search = await screen.findByRole("searchbox", { name: "Search saved passages" });

    await userEvent.type(search, "therese");
    expect(screen.getByTestId("bookmark-card")).toBeTruthy();
    await userEvent.clear(search);
    await userEvent.type(search, "church fathers");
    expect(screen.getByTestId("bookmark-card")).toBeTruthy();
    await userEvent.clear(search);
    await userEvent.type(search, "dwelling one");
    expect(screen.getByTestId("bookmark-card")).toBeTruthy();
  });

  it("restores failed concurrent removals once in deterministic newest-first order", async () => {
    let rejectFirst!: (error: Error) => void;
    let rejectSecond!: (error: Error) => void;
    state.removeBookmark
      .mockReturnValueOnce(new Promise((_, reject) => { rejectFirst = reject; }))
      .mockReturnValueOnce(new Promise((_, reject) => { rejectSecond = reject; }));
    render(<BookmarksPage />);
    await screen.findAllByTestId("bookmark-card");

    await userEvent.click(screen.getByRole("button", { name: "Remove 1" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove 2" }));
    rejectSecond(new Error("failed"));
    rejectFirst(new Error("failed"));

    await waitFor(() => {
      expect(screen.getAllByTestId("bookmark-card").map((item) => item.firstChild?.textContent)).toEqual(["1", "2", "3"]);
    });
  });

  it("does not restore an old account's failed removal after the token changes", async () => {
    let rejectRemoval!: (error: Error) => void;
    state.removeBookmark.mockReturnValueOnce(new Promise((_, reject) => { rejectRemoval = reject; }));
    state.getBookmarks
      .mockResolvedValueOnce([bookmark("1", "Old account")])
      .mockResolvedValueOnce([bookmark("9", "New account")]);
    const view = render(<BookmarksPage />);
    await screen.findByRole("button", { name: "Remove 1" });
    await userEvent.click(screen.getByRole("button", { name: "Remove 1" }));

    state.token = "new-token";
    view.rerender(<BookmarksPage />);
    expect(await screen.findByRole("button", { name: "Remove 9" })).toBeTruthy();
    rejectRemoval(new Error("failed"));

    await waitFor(() => expect(screen.queryByRole("button", { name: "Remove 1" })).toBeNull());
    expect(state.showToast).not.toHaveBeenCalled();
  });
});
