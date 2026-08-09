// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentInfo, ReaderChapter } from "@/lib/api";
import { DocumentReader } from "./DocumentReader";
import { createReaderReturnKey } from "@/lib/readerNavigation";

const api = vi.hoisted(() => ({
  getReadingProgress: vi.fn(),
  getReaderChapter: vi.fn(),
  getToc: vi.fn(),
  putReadingProgress: vi.fn(),
}));
const navigation = vi.hoisted(() => ({
  params: new Map<string, string>(),
  push: vi.fn(),
  back: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  ...api,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: navigation.back, push: navigation.push, replace: navigation.replace }),
  useSearchParams: () => ({ get: (key: string) => navigation.params.get(key) ?? null }),
}));

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ token: "token", mobileNavigationOpen: false, openMobileNavigation: vi.fn() }),
}));

vi.mock("./ReaderChrome", () => ({
  ReaderChrome: ({ currentChapterKey, onJump, onBack, onBrowseSections }: { currentChapterKey: string | null; onJump: (key: string) => void; onBack: () => void; onBrowseSections: () => void }) => (
    <div>
      <span data-testid="current-key">{currentChapterKey}</span>
      <button onClick={onBack}>Reader Back</button>
      <button onClick={() => onJump("chapter-b")}>Jump B</button>
      <button onClick={() => onJump("chapter-c")}>Jump C</button>
      <button onClick={onBrowseSections}>Browse sections</button>
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
  navigation.params = new Map([["chapter", "chapter-a"], ["from", "library"]]);
  navigation.push.mockReset();
  navigation.back.mockReset();
  navigation.replace.mockReset();
  sessionStorage.clear();
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
  it("keeps mobile app navigation and branding visible while loading", () => {
    api.getToc.mockReturnValue(new Promise(() => {}));

    render(<DocumentReader docId="doc-a" />);

    expect(screen.getByText("TheoCorpus")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open app navigation" })).toBeTruthy();
  });

  it("keeps mobile app navigation and branding visible after a load failure", async () => {
    api.getToc.mockRejectedValue(new Error("offline"));

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByText("This document couldn't be loaded.")).toBeTruthy();
    expect(screen.getByText("TheoCorpus")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open app navigation" })).toBeTruthy();
  });

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

describe("DocumentReader overview", () => {
  it("shows a Bible chapter grid before ordinary Library entry", async () => {
    navigation.params = new Map([["from", "library"]]);
    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByRole("heading", { name: "Document doc-a" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Choose a chapter" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Document doc-a chapter chapter-a" })).toBeTruthy();
    expect(api.getReaderChapter).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Document doc-a chapter chapter-b" }));
    expect(navigation.push).toHaveBeenCalledWith("/reader/doc-a?from=library&chapter=chapter-b");
  });

  it("lets long Bible books reveal chapters beyond the first batch", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockResolvedValue({
      document: { ...documentInfo("doc-a"), title: "Psalms" },
      chapters: Array.from({ length: 61 }, (_, index) => ({ chapter_key: `psalms/${index + 1}`, chapter_label: `Psalms ${index + 1}` })),
    });
    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByRole("button", { name: "Psalms chapter 30" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Psalms chapter 31" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show more chapters" }));
    expect(screen.getByRole("button", { name: "Psalms chapter 60" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show more chapters" }));
    expect(screen.getByRole("button", { name: "Psalms chapter 61" })).toBeTruthy();
  });

  it("offers valid saved progress", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getReadingProgress.mockResolvedValue({
      document_id: "doc-a", chapter_key: "chapter-b", chapter_label: "Chapter B",
      anchor: null, updated_at: "2026-08-08T00:00:00Z", collection: "bible",
      document_title: "Document doc-a", author: null,
    });
    render(<DocumentReader docId="doc-a" />);

    const continueButton = await screen.findByRole("button", { name: "Continue at Chapter B" });
    fireEvent.click(continueButton);
    expect(navigation.push).toHaveBeenCalledWith("/reader/doc-a?from=library&chapter=chapter-b");
  });

  it("does not block the overview while optional progress is still loading", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getReadingProgress.mockReturnValue(new Promise(() => {}));

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByRole("heading", { name: "Document doc-a" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start reading" })).toBeTruthy();
  });

  it("uses source-specific searchable section language and preserves original numbering", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockResolvedValue({
      document: { ...documentInfo("doc-a"), collection: "catechism", title: "Catechism" },
      chapters: Array.from({ length: 13 }, (_, index) => ({ chapter_key: `range-${index + 1}`, chapter_label: `CCC §§${index * 100}–${index * 100 + 99}` })),
    });
    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByRole("heading", { name: "Choose a paragraph range" })).toBeTruthy();
    const search = screen.getByRole("searchbox", { name: "Search paragraph ranges" });
    fireEvent.change(search, { target: { value: "1200" } });
    expect(screen.getByText("13")).toBeTruthy();
    expect(screen.getByText("CCC §§1200–1299")).toBeTruthy();
    expect(screen.queryByText("CCC §§0–99")).toBeNull();

    fireEvent.change(search, { target: { value: "1250" } });
    expect(screen.getByText("CCC §§1200–1299")).toBeTruthy();

    fireEvent.change(search, { target: { value: "99" } });
    expect(screen.getByText("CCC §§0–99")).toBeTruthy();
    expect(screen.queryByText("CCC §§900–999")).toBeNull();
  });

  it("labels Summa article-level TOCs accurately and incrementally reveals large lists", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockResolvedValue({
      document: { ...documentInfo("doc-a"), collection: "summa", title: "Summa Theologiae" },
      chapters: Array.from({ length: 61 }, (_, index) => ({
        chapter_key: `article-${index + 1}`,
        chapter_label: `Question 1 — Article ${index + 1}`,
      })),
    });
    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByRole("heading", { name: "Choose an article" })).toBeTruthy();
    expect(screen.getByText("Question 1 — Article 30")).toBeTruthy();
    expect(screen.queryByText("Question 1 — Article 31")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show more articles" }));
    fireEvent.click(screen.getByRole("button", { name: "Show more articles" }));
    expect(screen.getByText("Question 1 — Article 61")).toBeTruthy();
  });

  it("routes overview back controls to their validated in-app destination", async () => {
    navigation.params = new Map([["from", "search"]]);
    render(<DocumentReader docId="doc-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "Back to Search" }));
    expect(navigation.push).toHaveBeenCalledWith("/search");
    expect(navigation.back).not.toHaveBeenCalled();
  });

  it("routes the reader back control to its validated in-app destination", async () => {
    navigation.params = new Map([["from", "search"], ["chapter", "chapter-a"]]);
    render(<DocumentReader docId="doc-a" />);

    await screen.findByText("doc-a chapter-a");
    fireEvent.click(screen.getByRole("button", { name: "Reader Back" }));
    expect(navigation.push).toHaveBeenCalledWith("/search");
    expect(navigation.back).not.toHaveBeenCalled();
  });

  it("returns from reading to the overview while preserving its origin", async () => {
    navigation.params = new Map([["from", "history"], ["chapter", "chapter-a"], ["returnKey", "11111111-1111-4111-8111-111111111111"]]);
    render(<DocumentReader docId="doc-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "Browse sections" }));

    expect(navigation.replace).toHaveBeenCalledWith("/reader/doc-a?from=history&returnKey=11111111-1111-4111-8111-111111111111");
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("returns through exact same-tab history only when a valid marker exists", async () => {
    const returnKey = createReaderReturnKey("search");
    expect(returnKey).toBeTruthy();
    navigation.params = new Map([
      ["from", "search"],
      ["chapter", "chapter-a"],
      ["returnKey", returnKey!],
    ]);
    render(<DocumentReader docId="doc-a" />);

    await screen.findByText("doc-a chapter-a");
    fireEvent.click(screen.getByRole("button", { name: "Reader Back" }));
    expect(navigation.back).toHaveBeenCalledTimes(1);
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("replaces the overview entry when opening a chapter with a return marker", async () => {
    const returnKey = createReaderReturnKey("library");
    expect(returnKey).toBeTruthy();
    navigation.params = new Map([["from", "library"], ["returnKey", returnKey!]]);
    render(<DocumentReader docId="doc-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "Document doc-a chapter chapter-b" }));
    expect(navigation.replace).toHaveBeenCalledWith(`/reader/doc-a?from=library&chapter=chapter-b&returnKey=${returnKey}`);
    expect(navigation.push).not.toHaveBeenCalled();
  });
});
