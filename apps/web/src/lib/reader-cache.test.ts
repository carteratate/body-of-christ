import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ReaderChapter, TocResponse } from "@/lib/api";
import { __resetClientCachesForTests } from "./client-cache";
import {
  invalidateReaderDocument,
  isChapterCached,
  loadChapter,
  loadEntryChapter,
  loadToc,
} from "./reader-cache";

const api = vi.hoisted(() => ({
  getReaderChapter: vi.fn(),
  getToc: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

function chapter(key: string, highlight: string | null = null): ReaderChapter {
  return {
    document: { id: "doc", collection: "summa", title: "Summa", author: null, year: null, metadata: null, chunk_count: 3 },
    chapter_key: key,
    chapter_label: key,
    passages: [],
    prev_chapter_key: null,
    next_chapter_key: null,
    highlight_anchor: highlight,
  };
}

const toc: TocResponse = { document: chapter("x").document, chapters: [] };
const signedIn = { token: "token-1" };

beforeEach(() => {
  __resetClientCachesForTests();
  vi.clearAllMocks();
  api.getToc.mockResolvedValue(toc);
  api.getReaderChapter.mockImplementation(async (_token: string, _docId: string, options: { chapter?: string; anchor?: string }) =>
    chapter(options.chapter ?? "entry", options.anchor ?? null));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("reader cache", () => {
  it("forgets contents and chapters after thirty minutes", async () => {
    vi.useFakeTimers();
    await loadToc(signedIn, "doc");
    await loadChapter(signedIn, "doc", "a");

    vi.advanceTimersByTime(30 * 60 * 1000 - 1);
    expect(isChapterCached(signedIn, "doc", "a")).toBe(true);
    vi.advanceTimersByTime(1);
    expect(isChapterCached(signedIn, "doc", "a")).toBe(false);
    await loadToc(signedIn, "doc");
    expect(api.getToc).toHaveBeenCalledTimes(2);
  });

  it("shares a signed-in entry across token refreshes", async () => {
    await loadToc({ token: "token-1" }, "doc");
    await loadToc({ token: "token-2" }, "doc");

    expect(api.getToc).toHaveBeenCalledTimes(1);
  });

  it("keeps guest sessions apart from each other and from signed-in readers", async () => {
    await loadToc(signedIn, "doc");
    await loadToc({ token: null, guestToken: "guest-1" }, "doc");
    await loadToc({ token: null, guestToken: "guest-2" }, "doc");
    await loadToc({ token: null, guestToken: "guest-1" }, "doc");

    expect(api.getToc).toHaveBeenCalledTimes(3);
    expect(api.getToc).toHaveBeenLastCalledWith("", "doc", expect.any(AbortSignal), "guest-2");
  });

  it("stores an anchor-opened chapter under its key, without the highlight", async () => {
    const opened = await loadEntryChapter(signedIn, "doc", { anchor: "p-7" });
    expect(opened.highlight_anchor).toBe("p-7");
    expect(isChapterCached(signedIn, "doc", "entry")).toBe(true);

    const reused = await loadChapter(signedIn, "doc", "entry");
    expect(reused.highlight_anchor).toBeNull();
    expect(api.getReaderChapter).toHaveBeenCalledTimes(1);
  });

  it("evicts one document's contents and chapters only", async () => {
    await loadToc(signedIn, "doc");
    await loadToc(signedIn, "doc-2");
    await loadChapter(signedIn, "doc", "a");
    await loadChapter(signedIn, "doc-2", "a");

    invalidateReaderDocument(signedIn, "doc");

    expect(isChapterCached(signedIn, "doc", "a")).toBe(false);
    expect(isChapterCached(signedIn, "doc-2", "a")).toBe(true);
    await loadToc(signedIn, "doc");
    await loadToc(signedIn, "doc-2");
    expect(api.getToc).toHaveBeenCalledTimes(3);
  });

  it("keeps only the four most recent tables of contents", async () => {
    for (const docId of ["d1", "d2", "d3", "d4", "d5"]) await loadToc(signedIn, docId);
    await loadToc(signedIn, "d5");
    await loadToc(signedIn, "d2");
    await loadToc(signedIn, "d1");

    expect(api.getToc).toHaveBeenCalledTimes(6);
  });
});
