// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentInfo, ReaderChapter } from "@/lib/api";
import { DocumentReader } from "./DocumentReader";
import { createReaderReturnKey } from "@/lib/readerNavigation";
import { __resetClientCachesForTests } from "@/lib/client-cache";
import { isChapterCached } from "@/lib/reader-cache";

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

const appContext = vi.hoisted(() => ({ token: "token" as string | null }));
const trial = vi.hoisted(() => ({ guestToken: "" }));

vi.mock("@/lib/trial", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/trial")>(),
  getGuestSessionToken: () => trial.guestToken,
}));

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ token: appContext.token, mobileNavigationOpen: false, openMobileNavigation: vi.fn() }),
}));

vi.mock("./ReaderChrome", () => ({
  ReaderChrome: ({ currentChapterKey, tocStatus, onRetryToc, onJump, onBack, onBrowseSections }: { currentChapterKey: string | null; tocStatus?: string; onRetryToc?: () => void; onJump: (key: string) => void; onBack: () => void; onBrowseSections: () => void }) => (
    <div>
      <span data-testid="current-key">{currentChapterKey}</span>
      <span data-testid="toc-status">{tocStatus}</span>
      <button onClick={onRetryToc}>Retry contents</button>
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

function chapterCalls(key: string) {
  return api.getReaderChapter.mock.calls.filter((call) => call[2]?.chapter === key);
}

function nearBottom(scroller: HTMLDivElement) {
  Object.defineProperties(scroller, {
    scrollHeight: { value: 1000, configurable: true },
    clientHeight: { value: 500, configurable: true },
    scrollTop: { value: 450, configurable: true },
  });
}

beforeEach(() => {
  __resetClientCachesForTests();
  appContext.token = "token";
  trial.guestToken = "";
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
    api.getReaderChapter.mockRejectedValue(new Error("offline"));

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByText("This document couldn't be loaded.")).toBeTruthy();
    expect(screen.getByText("TheoCorpus")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open app navigation" })).toBeTruthy();
  });

  it("shows the chapter before the table of contents arrives", async () => {
    const toc = deferred<{ document: DocumentInfo; chapters: { chapter_key: string; chapter_label: string }[] }>();
    api.getToc.mockReturnValue(toc.promise);

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByText("doc-a chapter-a")).toBeTruthy();
    expect(screen.getByTestId("toc-status").textContent).toBe("loading");

    toc.resolve({ document: documentInfo("doc-a"), chapters: [{ chapter_key: "chapter-a", chapter_label: "chapter-a" }] });
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));
  });

  it("keeps the chapter when the table of contents fails, and retries it", async () => {
    const toc = deferred<never>();
    api.getToc.mockReturnValueOnce(toc.promise);

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    toc.reject(new Error("offline"));

    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("error"));
    expect(screen.getByText("doc-a chapter-a")).toBeTruthy();
    expect(screen.queryByText("This document couldn't be loaded.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Retry contents" }));
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));
    expect(api.getToc).toHaveBeenCalledTimes(2);
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

    await screen.findByText("We couldn't save your reading place yet.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(api.putReadingProgress).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText("We couldn't save your reading place yet.")).toBeNull());
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
    expect(screen.queryByText("We couldn't save your reading place yet.")).toBeNull();
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
    nearBottom(scroller);
    fireEvent.scroll(scroller);
    await waitFor(() => expect(chapterCalls("chapter-b").length).toBeGreaterThan(0));

    fireEvent.click(screen.getByRole("button", { name: "Jump C" }));
    await screen.findByText("Chapter couldn't be loaded.");
    await act(async () => {
      appendB.resolve(chapter("doc-a", "chapter-b"));
      await appendB.promise;
    });
    expect(screen.queryByText("doc-a chapter-b")).toBeNull();
    fireEvent.scroll(scroller);

    expect(await screen.findByText("doc-a chapter-b")).toBeTruthy();
  });
});

describe("DocumentReader caching", () => {
  it("reuses the overview's table of contents when a section opens", async () => {
    navigation.params = new Map([["from", "library"]]);
    const view = render(<DocumentReader docId="doc-a" />);
    await screen.findByRole("heading", { name: "Document doc-a" });

    navigation.params = new Map([["from", "library"], ["chapter", "chapter-b"]]);
    view.rerender(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-b");
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));

    expect(api.getToc).toHaveBeenCalledTimes(1);
  });

  it("reopens a document from memory", async () => {
    const first = render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));
    first.unmount();

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));

    expect(api.getToc).toHaveBeenCalledTimes(1);
    expect(chapterCalls("chapter-a")).toHaveLength(1);
  });

  it("does not remember a failed chapter", async () => {
    api.getReaderChapter
      .mockRejectedValueOnce(new Error("offline"))
      .mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => chapter(docId, options.chapter ?? "chapter-a"));

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("This document couldn't be loaded.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("doc-a chapter-a")).toBeTruthy();
    expect(chapterCalls("chapter-a")).toHaveLength(2);
  });

  it("refreshes the contents when a chapter from them no longer exists", async () => {
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") throw new Error("API error 404");
      return chapter(docId, "chapter-a");
    });

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));
    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));

    await screen.findByText("Chapter couldn't be loaded.");
    expect(isChapterCached({ token: "token" }, "doc-a", "chapter-a")).toBe(false);
    await waitFor(() => expect(api.getToc).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("toc-status").textContent).toBe("ready");
  });

  it("offers a contents retry when a refresh fails before any contents arrived", async () => {
    const firstToc = deferred<never>();
    api.getToc.mockReturnValueOnce(firstToc.promise).mockRejectedValueOnce(new Error("offline"));
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") throw new Error("API error 404");
      return chapter(docId, "chapter-a");
    });

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));
    await screen.findByText("Chapter couldn't be loaded.");

    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("error"));
  });

  it("refetches the contents once when their passage count disagrees with the chapter", async () => {
    api.getToc.mockImplementation(async (_token: string, docId: string) => ({
      document: { ...documentInfo(docId), chunk_count: 99 },
      chapters: [{ chapter_key: "chapter-a", chapter_label: "chapter-a" }],
    }));

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");

    await waitFor(() => expect(api.getToc).toHaveBeenCalledTimes(2));
    expect(isChapterCached({ token: "token" }, "doc-a", "chapter-a")).toBe(false);
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));
    await act(async () => { await Promise.resolve(); });
    expect(api.getToc).toHaveBeenCalledTimes(2);
  });

  it("does not carry an unresolved mismatch into the next document", async () => {
    api.getToc.mockImplementation(async (_token: string, docId: string) => ({
      document: { ...documentInfo(docId), chunk_count: docId === "doc-a" ? 99 : 3 },
      chapters: [{ chapter_key: "chapter-a", chapter_label: "chapter-a" }],
    }));
    const view = render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(api.getToc).toHaveBeenCalledTimes(2));

    view.rerender(<DocumentReader docId="doc-b" />);
    await screen.findByText("doc-b chapter-a");
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));

    expect(api.getToc.mock.calls.filter((call) => call[1] === "doc-b")).toHaveLength(1);
    expect(isChapterCached({ token: "token" }, "doc-b", "chapter-a")).toBe(true);
  });

  it("reads as the guest session, and shares the guest overview's contents", async () => {
    appContext.token = null;
    trial.guestToken = "guest-1";
    navigation.params = new Map([["from", "search"]]);
    const view = render(<DocumentReader docId="doc-a" isGuest />);
    await screen.findByRole("heading", { name: "Document doc-a" });

    navigation.params = new Map([["from", "search"], ["chapter", "chapter-b"]]);
    view.rerender(<DocumentReader docId="doc-a" isGuest />);
    await screen.findByText("doc-a chapter-b");
    await waitFor(() => expect(screen.getByTestId("toc-status").textContent).toBe("ready"));

    expect(api.getToc).toHaveBeenCalledTimes(1);
    expect(api.getToc).toHaveBeenCalledWith("", "doc-a", expect.any(AbortSignal), "guest-1");
    expect(chapterCalls("chapter-b")[0].slice(0, 2)).toEqual(["", "doc-a"]);
    expect(chapterCalls("chapter-b")[0][2].guestToken).toBe("guest-1");
    expect(isChapterCached({ token: "token" }, "doc-a", "chapter-b")).toBe(false);
    expect(isChapterCached({ token: null, guestToken: "guest-1" }, "doc-a", "chapter-b")).toBe(true);
  });

  it("keeps the reading position through a token refresh", async () => {
    const view = render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));
    await screen.findByText("doc-a chapter-b");
    const tocCalls = api.getToc.mock.calls.length;

    appContext.token = "refreshed-token";
    view.rerender(<DocumentReader docId="doc-a" />);
    await Promise.resolve();

    expect(screen.getByText("doc-a chapter-b")).toBeTruthy();
    expect(screen.getByTestId("current-key").textContent).toBe("chapter-b");
    expect(api.getToc).toHaveBeenCalledTimes(tocCalls);
  });
});

describe("DocumentReader next-chapter prefetch", () => {
  function linkedChapter(docId: string, key: string): ReaderChapter {
    const order = ["chapter-a", "chapter-b", "chapter-c"];
    const index = order.indexOf(key);
    return { ...chapter(docId, key), prev_chapter_key: order[index - 1] ?? null, next_chapter_key: order[index + 1] ?? null };
  }

  beforeEach(() => {
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => linkedChapter(docId, options.chapter ?? "chapter-a"));
  });

  it("warms the next chapter without showing it", async () => {
    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");

    await waitFor(() => expect(chapterCalls("chapter-b")).toHaveLength(1));
    expect(screen.queryByText("doc-a chapter-b")).toBeNull();
    expect(screen.queryByLabelText("Loading chapter")).toBeNull();
    expect(screen.getByTestId("current-key").textContent).toBe("chapter-a");
  });

  it("serves Next from memory without a loading state", async () => {
    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(chapterCalls("chapter-b")).toHaveLength(1));
    await act(async () => { await Promise.resolve(); });

    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));

    expect(screen.queryByLabelText("Loading chapter")).toBeNull();
    expect(await screen.findByText("doc-a chapter-b")).toBeTruthy();
    expect(chapterCalls("chapter-b")).toHaveLength(1);
  });

  it("appends a prefetched chapter on scroll without another request", async () => {
    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(chapterCalls("chapter-b")).toHaveLength(1));
    const scroller = document.querySelector(".reader-content") as HTMLDivElement;
    nearBottom(scroller);
    fireEvent.scroll(scroller);

    expect(await screen.findByText("doc-a chapter-b")).toBeTruthy();
    expect(screen.getByText("doc-a chapter-a")).toBeTruthy();
    expect(chapterCalls("chapter-b")).toHaveLength(1);
  });

  it("never lets a prefetch override a jump in flight", async () => {
    const prefetchB = deferred<ReaderChapter>();
    const jumpC = deferred<ReaderChapter>();
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") return prefetchB.promise;
      if (options.chapter === "chapter-c") return jumpC.promise;
      return linkedChapter(docId, "chapter-a");
    });

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(chapterCalls("chapter-b")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Jump C" }));

    await act(async () => {
      prefetchB.resolve(linkedChapter("doc-a", "chapter-b"));
      await prefetchB.promise;
    });
    expect(screen.getByTestId("current-key").textContent).toBe("chapter-a");
    expect(screen.queryByText("doc-a chapter-b")).toBeNull();
    expect(screen.getByLabelText("Loading chapter")).toBeTruthy();

    jumpC.resolve(linkedChapter("doc-a", "chapter-c"));
    await waitFor(() => expect(screen.getByTestId("current-key").textContent).toBe("chapter-c"));
  });

  it("joins a prefetch already in flight instead of requesting again", async () => {
    const requestB = deferred<ReaderChapter>();
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") return requestB.promise;
      return linkedChapter(docId, options.chapter ?? "chapter-a");
    });

    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(chapterCalls("chapter-b")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));

    requestB.resolve(linkedChapter("doc-a", "chapter-b"));
    expect(await screen.findByText("doc-a chapter-b")).toBeTruthy();
    expect(chapterCalls("chapter-b")).toHaveLength(1);
  });

  it("cancels a prefetch still in flight when the reader closes", async () => {
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") return new Promise(() => {});
      return linkedChapter(docId, "chapter-a");
    });

    const view = render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    await waitFor(() => expect(chapterCalls("chapter-b")).toHaveLength(1));
    const signal = chapterCalls("chapter-b")[0][2].signal as AbortSignal;
    expect(signal.aborted).toBe(false);

    view.unmount();
    await waitFor(() => expect(signal.aborted).toBe(true));
  });

  it("skips prefetching when the browser asks to save data", async () => {
    const idle = vi.fn(() => 1);
    Object.defineProperty(window, "requestIdleCallback", { value: idle, configurable: true });
    Object.defineProperty(window, "cancelIdleCallback", { value: vi.fn(), configurable: true });
    Object.defineProperty(navigator, "connection", { value: { saveData: true }, configurable: true });
    try {
      render(<DocumentReader docId="doc-a" />);
      await screen.findByText("doc-a chapter-a");
      await act(async () => { await Promise.resolve(); });
      expect((await api.getReaderChapter.mock.results[0].value as ReaderChapter).next_chapter_key).toBe("chapter-b");
      expect(idle).not.toHaveBeenCalled();
      expect(chapterCalls("chapter-b")).toHaveLength(0);
    } finally {
      Reflect.deleteProperty(navigator, "connection");
      Reflect.deleteProperty(window, "requestIdleCallback");
      Reflect.deleteProperty(window, "cancelIdleCallback");
    }
  });

  it("does not prefetch the previous document's next chapter when the document changes", async () => {
    Object.defineProperty(window, "requestIdleCallback", { value: (callback: () => void) => { callback(); return 1; }, configurable: true });
    Object.defineProperty(window, "cancelIdleCallback", { value: vi.fn(), configurable: true });
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (docId === "doc-a") return { ...chapter(docId, options.chapter ?? "chapter-a"), next_chapter_key: "only-in-a" };
      return chapter(docId, options.chapter ?? "chapter-a");
    });
    try {
      const view = render(<DocumentReader docId="doc-a" />);
      await screen.findByText("doc-a chapter-a");
      await waitFor(() => expect(api.getReaderChapter).toHaveBeenCalledWith("token", "doc-a", expect.objectContaining({ chapter: "only-in-a" })));

      view.rerender(<DocumentReader docId="doc-b" />);
      await screen.findByText("doc-b chapter-a");

      expect(api.getReaderChapter).not.toHaveBeenCalledWith("token", "doc-b", expect.objectContaining({ chapter: "only-in-a" }));
    } finally {
      Reflect.deleteProperty(window, "requestIdleCallback");
      Reflect.deleteProperty(window, "cancelIdleCallback");
    }
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
