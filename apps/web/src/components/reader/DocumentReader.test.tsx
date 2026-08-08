// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentInfo, ReaderChapter } from "@/lib/api";
import { DocumentReader } from "./DocumentReader";

const api = vi.hoisted(() => ({
  getReadingProgress: vi.fn(),
  getReaderChapter: vi.fn(),
  getToc: vi.fn(),
  putReadingProgress: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  ...api,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ token: "token" }),
}));

vi.mock("./ReaderChrome", () => ({
  ReaderChrome: ({ currentChapterKey, onJump }: { currentChapterKey: string | null; onJump: (key: string) => void }) => (
    <div>
      <span data-testid="current-key">{currentChapterKey}</span>
      <button onClick={() => onJump("chapter-b")}>Jump B</button>
      <button onClick={() => onJump("chapter-c")}>Jump C</button>
    </div>
  ),
}));

vi.mock("./ContentsDrawer", () => ({ ContentsDrawer: () => null }));
vi.mock("./ChapterSection", () => ({
  ChapterSection: ({ chapter }: { chapter: ReaderChapter }) => <section data-chapter-key={chapter.chapter_key}>{chapter.chapter_label}</section>,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function documentInfo(id: string): DocumentInfo {
  return { id, collection: "bible", title: `Document ${id}`, author: null, year: null, metadata: null, chunk_count: 3 };
}

function chapter(docId: string, key: string): ReaderChapter {
  return {
    document: documentInfo(docId),
    chapter_key: key,
    chapter_label: `${docId} ${key}`,
    passages: [],
    prev_chapter_key: null,
    next_chapter_key: null,
    highlight_anchor: null,
  };
}

beforeEach(() => {
  api.getReadingProgress.mockResolvedValue(null);
  api.getToc.mockImplementation(async (_token: string, docId: string) => ({
    document: documentInfo(docId),
    chapters: ["chapter-a", "chapter-b", "chapter-c"].map((key) => ({ chapter_key: key, chapter_label: key })),
  }));
  api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => chapter(docId, options.chapter ?? "chapter-a"));
  api.putReadingProgress.mockResolvedValue({});
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DocumentReader request ordering", () => {
  it("ignores an older chapter response that resolves after a newer jump", async () => {
    const requestB = deferred<ReaderChapter>();
    const requestC = deferred<ReaderChapter>();
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") return requestB.promise;
      if (options.chapter === "chapter-c") return requestC.promise;
      return chapter(docId, "chapter-a");
    });

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));
    fireEvent.click(screen.getByRole("button", { name: "Jump C" }));

    requestC.resolve(chapter("doc-a", "chapter-c"));
    await waitFor(() => expect(screen.getByTestId("current-key").textContent).toBe("chapter-c"));
    requestB.resolve(chapter("doc-a", "chapter-b"));
    await Promise.resolve();

    expect(screen.getByTestId("current-key").textContent).toBe("chapter-c");
    expect(screen.queryByText("doc-a chapter-b")).toBeNull();
  });

  it("keeps the displayed chapter and progress unchanged when a jump fails", async () => {
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") throw new Error("unavailable");
      return chapter(docId, "chapter-a");
    });

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));
    await screen.findByText("Chapter couldn't be loaded.");

    expect(screen.getByTestId("current-key").textContent).toBe("chapter-a");
    expect(api.putReadingProgress).not.toHaveBeenCalledWith("token", "doc-a", "chapter-b");
  });

  it("does not let an old document save consume the new document queue", async () => {
    const saveA = deferred<object>();
    api.putReadingProgress.mockImplementation(async (_token: string, docId: string) => {
      if (docId === "doc-a") return saveA.promise;
      return {};
    });

    const view = render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(api.putReadingProgress).toHaveBeenCalledWith("token", "doc-a", "chapter-a"));

    view.rerender(<DocumentReader docId="doc-b" />);
    await screen.findByText("doc-b chapter-a");
    await waitFor(() => expect(api.putReadingProgress).toHaveBeenCalledWith("token", "doc-b", "chapter-a"));
    expect(api.putReadingProgress).not.toHaveBeenCalledWith("token", "doc-a", "chapter-b");

    saveA.resolve({});
  });

  it("retains a failed progress save and lets the reader retry it", async () => {
    api.putReadingProgress.mockRejectedValueOnce(new Error("offline")).mockResolvedValue({});
    render(<DocumentReader docId="doc-a" />);

    await screen.findByText("Your reading place has not synced yet.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(api.putReadingProgress).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText("Your reading place has not synced yet.")).toBeNull());
  });

  it("prefers the newest queued location when an older save fails", async () => {
    const saveA = deferred<object>();
    api.putReadingProgress.mockImplementation(async (_token: string, _docId: string, key: string) => {
      if (key === "chapter-a") return saveA.promise;
      return {};
    });
    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(api.putReadingProgress).toHaveBeenCalledWith("token", "doc-a", "chapter-a"));

    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));
    await screen.findByText("doc-a chapter-b");
    saveA.reject(new Error("offline"));

    await waitFor(() => expect(api.putReadingProgress).toHaveBeenCalledWith("token", "doc-a", "chapter-b"));
    expect(screen.queryByText("Your reading place has not synced yet.")).toBeNull();
  });

  it("allows a stale append to be requested again after a replacement fails", async () => {
    const appendB = deferred<ReaderChapter>();
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") return appendB.promise;
      if (options.chapter === "chapter-c") throw new Error("unavailable");
      return { ...chapter(docId, "chapter-a"), next_chapter_key: "chapter-b" };
    });
    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    const scroller = document.querySelector(".reader-content") as HTMLDivElement;
    Object.defineProperties(scroller, {
      scrollHeight: { value: 1000, configurable: true },
      clientHeight: { value: 500, configurable: true },
      scrollTop: { value: 450, configurable: true },
    });
    fireEvent.scroll(scroller);
    await waitFor(() => expect(api.getReaderChapter).toHaveBeenCalledWith("token", "doc-a", { chapter: "chapter-b" }));

    fireEvent.click(screen.getByRole("button", { name: "Jump C" }));
    await screen.findByText("Chapter couldn't be loaded.");
    await act(async () => {
      appendB.resolve(chapter("doc-a", "chapter-b"));
      await appendB.promise;
    });
    fireEvent.scroll(scroller);

    await waitFor(() => {
      const bCalls = api.getReaderChapter.mock.calls.filter((call) => call[2]?.chapter === "chapter-b");
      expect(bCalls).toHaveLength(2);
    });
  });
});
