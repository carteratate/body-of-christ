// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import type { DocumentInfo, ReaderChapter } from "@/lib/api";
import { DocumentReader } from "./DocumentReader";
import { markReaderReturn, newReaderReturnKey } from "@/lib/readerNavigation";
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
  prefetch: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  ...api,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: navigation.back, push: navigation.push, replace: navigation.replace, prefetch: navigation.prefetch }),
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
  ChapterSection: ({ chapter }: { chapter: ReaderChapter }) => (
    <section data-chapter-key={chapter.chapter_key}>
      {chapter.chapter_label}
      {chapter.passages.map((p) => <p key={p.id} id={`anchor-${p.anchor}`}>{p.content}</p>)}
    </section>
  ),
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

let replaceState: MockInstance<History["replaceState"]>;
let pushState: MockInstance<History["pushState"]>;

beforeEach(() => {
  replaceState = vi.spyOn(window.history, "replaceState");
  pushState = vi.spyOn(window.history, "pushState");
  __resetClientCachesForTests();
  appContext.token = "token";
  trial.guestToken = "";
  navigation.params = new Map([["chapter", "chapter-a"], ["from", "library"]]);
  navigation.push.mockReset();
  navigation.back.mockReset();
  navigation.replace.mockReset();
  navigation.prefetch.mockReset();
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
  replaceState.mockRestore();
  pushState.mockRestore();
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
    expect(pushState).toHaveBeenCalledWith(null, "", "/reader/doc-a?from=library&chapter=chapter-b");
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
    expect(pushState).toHaveBeenCalledWith(null, "", "/reader/doc-a?from=library&chapter=chapter-b");
  });

  describe("with a contents tree", () => {
    const tree = [{
      key: "I", kind: "part", label: "First Part", short_label: "I · First Part", chapter_key: "chapter-a",
      anchor: null, range_label: "Qq. 1–2", children: [
        { key: "I/q1", kind: "question", label: "Q1", short_label: "Q. 1 · Sacred Doctrine", chapter_key: "chapter-a", anchor: null, range_label: null, children: [
          { key: "I/q1/a1", kind: "article", label: "A1", short_label: "Art. 1 · Whether", chapter_key: "chapter-a", anchor: null, range_label: null, children: [
            { key: "I/q1/a1/h", kind: "heading", label: "I answer that", short_label: "I answer that", chapter_key: "chapter-a", anchor: "a/3", range_label: null, children: [] },
          ] },
          { key: "I/q1/a2", kind: "article", label: "A2", short_label: "Art. 2 · Whether again", chapter_key: "chapter-b", anchor: null, range_label: null, children: [] },
        ] },
      ],
    }];

    beforeEach(() => {
      navigation.params = new Map([["from", "library"]]);
      api.getToc.mockImplementation(async (_token: string, docId: string) => ({
        document: { ...documentInfo(docId), collection: "summa", title: "Summa Theologiae" },
        chapters: ["chapter-a", "chapter-b"].map((key) => ({ chapter_key: key, chapter_label: key })),
        contents: tree,
      }));
    });

    it("shows the tree instead of the flat list, and counts its kinds", async () => {
      render(<DocumentReader docId="doc-a" />);

      expect(await screen.findByRole("tree", { name: "Contents" })).toBeTruthy();
      expect(screen.getByRole("heading", { name: "Contents" })).toBeTruthy();
      expect(screen.getByText(/3 passages · 1 part · 1 question · 2 articles/)).toBeTruthy();
      expect(screen.queryByText(/Show more/)).toBeNull();
      expect(screen.getAllByRole("treeitem").map((item) => item.textContent)).toEqual(["I · First PartQq. 1–2"]);
    });

    it("opens an article, and a heading at its anchor", async () => {
      render(<DocumentReader docId="doc-a" />);
      fireEvent.click(await screen.findByText("I · First Part"));
      fireEvent.click(screen.getByText("Q. 1 · Sacred Doctrine"));
      fireEvent.click(screen.getByText("Art. 2 · Whether again"));
      expect(pushState).toHaveBeenLastCalledWith(null, "", "/reader/doc-a?from=library&chapter=chapter-b");

      fireEvent.click(screen.getByText("Art. 1 · Whether"));   // has its own heading: opens
      expect(pushState).toHaveBeenLastCalledWith(null, "", "/reader/doc-a?from=library&chapter=chapter-a");
    });

    it("opens a heading with its anchor", async () => {
      render(<DocumentReader docId="doc-a" />);
      const search = await screen.findByPlaceholderText("Search contents");
      fireEvent.change(search, { target: { value: "answer" } });
      fireEvent.click(screen.getByText("I answer that"));
      expect(pushState).toHaveBeenLastCalledWith(null, "", "/reader/doc-a?from=library&chapter=chapter-a&anchor=a%2F3");
    });

    it("opens with every branch closed, even with saved progress", async () => {
      api.getReadingProgress.mockResolvedValue({
        document_id: "doc-a", chapter_key: "chapter-b", chapter_label: "Chapter B",
        anchor: null, updated_at: "2026-08-08T00:00:00Z", collection: "summa",
        document_title: "Summa Theologiae", author: null,
      });
      render(<DocumentReader docId="doc-a" />);

      expect(await screen.findByRole("button", { name: "Continue at Chapter B" })).toBeTruthy();
      expect(screen.getAllByRole("treeitem").map((item) => item.getAttribute("aria-expanded"))).toEqual(["false"]);
    });
  });

  it("does not block the overview while optional progress is still loading", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getReadingProgress.mockReturnValue(new Promise(() => {}));

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByRole("heading", { name: "Document doc-a" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start reading" })).toBeTruthy();
  });

  it("offers only Continue when there is saved progress, and Start reading when there is none", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getReadingProgress.mockResolvedValue({
      document_id: "doc-a", chapter_key: "chapter-b", chapter_label: "Chapter B",
      anchor: null, updated_at: "2026-08-08T00:00:00Z", collection: "bible",
      document_title: "Document doc-a", author: null,
    });
    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByRole("button", { name: "Continue at Chapter B" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start from the beginning" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Start reading" })).toBeNull();
  });

  it("keeps the section search and expanded list through a token refresh", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockResolvedValue({
      document: { ...documentInfo("doc-a"), collection: "summa", title: "Summa Theologiae" },
      chapters: Array.from({ length: 61 }, (_, index) => ({
        chapter_key: `article-${index + 1}`,
        chapter_label: `Question 1 — Article ${index + 1}`,
      })),
    });
    const view = render(<DocumentReader docId="doc-a" />);
    await screen.findByRole("heading", { name: "Choose an article" });
    fireEvent.click(screen.getByRole("button", { name: "Show more articles" }));
    expect(screen.getByText("Question 1 — Article 45")).toBeTruthy();
    const progressCalls = api.getReadingProgress.mock.calls.length;

    appContext.token = "refreshed-token";
    view.rerender(<DocumentReader docId="doc-a" />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText("Question 1 — Article 45")).toBeTruthy();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search articles" }), { target: { value: "Article 4" } });
    appContext.token = "refreshed-again";
    view.rerender(<DocumentReader docId="doc-a" />);
    await act(async () => { await Promise.resolve(); });

    expect((screen.getByRole("searchbox", { name: "Search articles" }) as HTMLInputElement).value).toBe("Article 4");
    expect(api.getReadingProgress).toHaveBeenCalledTimes(progressCalls);
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

    // Same route, new search params: the History API, not a server navigation.
    expect(replaceState).toHaveBeenCalledWith(null, "", "/reader/doc-a?from=history&returnKey=11111111-1111-4111-8111-111111111111");
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("keeps guest params when returning from reading to the overview", async () => {
    appContext.token = null;
    trial.guestToken = "guest-token";
    navigation.params = new Map([["from", "search"], ["chapter", "chapter-a"], ["preview", "1"], ["guideBack", "1"]]);
    render(<DocumentReader docId="doc-a" isGuest />);

    fireEvent.click(await screen.findByRole("button", { name: "Browse sections" }));

    expect(replaceState).toHaveBeenCalledWith(null, "", "/reader/guest/doc-a?from=search&preview=1&guideBack=1");
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  it("returns through exact same-tab history only when a valid marker exists", async () => {
    const returnKey = newReaderReturnKey();
    markReaderReturn(returnKey, "search");
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
    const returnKey = newReaderReturnKey();
    markReaderReturn(returnKey, "library");
    expect(returnKey).toBeTruthy();
    navigation.params = new Map([["from", "library"], ["returnKey", returnKey!]]);
    render(<DocumentReader docId="doc-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "Document doc-a chapter chapter-b" }));
    expect(replaceState).toHaveBeenCalledWith(null, "", `/reader/doc-a?from=library&chapter=chapter-b&returnKey=${returnKey}`);
    expect(pushState).not.toHaveBeenCalled();
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(navigation.push).not.toHaveBeenCalled();
  });

  it("pushes, not replaces, when the URL has a return key but this tab has no marker for it", async () => {
    // A cmd-click tab or a pasted URL: browser Back must return to the overview.
    navigation.params = new Map([["from", "library"], ["returnKey", "11111111-1111-4111-8111-111111111111"]]);
    render(<DocumentReader docId="doc-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "Document doc-a chapter chapter-b" }));
    expect(pushState).toHaveBeenCalledWith(null, "", "/reader/doc-a?from=library&chapter=chapter-b&returnKey=11111111-1111-4111-8111-111111111111");
    expect(replaceState).not.toHaveBeenCalled();
  });

  it("pushes a history entry when opening a chapter without a return marker", async () => {
    navigation.params = new Map([["from", "library"]]);
    render(<DocumentReader docId="doc-a" />);

    fireEvent.click(await screen.findByRole("button", { name: "Document doc-a chapter chapter-b" }));
    // A pushed entry lets browser Back return to the overview.
    expect(pushState).toHaveBeenCalledWith(null, "", "/reader/doc-a?from=library&chapter=chapter-b");
    expect(replaceState).not.toHaveBeenCalled();
    expect(navigation.push).not.toHaveBeenCalled();
  });
});

describe("DocumentReader back navigation", () => {
  it("prefetches the fallback page when Back will open it rather than pop history", async () => {
    navigation.params = new Map([["from", "saved"], ["chapter", "chapter-a"]]);
    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    expect(navigation.prefetch).toHaveBeenCalledWith("/bookmarks");

    fireEvent.click(screen.getByRole("button", { name: "Reader Back" }));
    expect(navigation.push).toHaveBeenCalledWith("/bookmarks");
  });

  it("does not prefetch when Back will return through same-tab history", async () => {
    const returnKey = newReaderReturnKey();
    markReaderReturn(returnKey, "library");
    navigation.params = new Map([["from", "library"], ["returnKey", returnKey!]]);
    render(<DocumentReader docId="doc-a" />);
    await screen.findByRole("button", { name: "Document doc-a chapter chapter-b" });
    expect(navigation.prefetch).not.toHaveBeenCalled();
  });

  it("prefetches the guest search page for a guest, keeping preview", async () => {
    appContext.token = null;
    trial.guestToken = "guest-token";
    navigation.params = new Map([["from", "search"], ["chapter", "chapter-a"], ["preview", "1"]]);
    render(<DocumentReader docId="doc-a" isGuest />);
    await screen.findByText("doc-a chapter-a");
    expect(navigation.prefetch).toHaveBeenCalledWith("/search/guest?preview=1");
    fireEvent.click(screen.getByRole("button", { name: "Reader Back" }));
    expect(navigation.push).toHaveBeenCalledWith("/search/guest?preview=1");
  });
});

describe("DocumentReader excerpt-only documents (issue #265)", () => {
  it("shows the notice and the source link instead of the text", async () => {
    const { ReaderRestrictedError } = await import("@/lib/api");
    api.getReaderChapter.mockRejectedValue(new ReaderRestrictedError("https://example.org/libertas"));
    api.getToc.mockRejectedValue(new ReaderRestrictedError("https://example.org/libertas"));

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByText("The full text of this document isn't available on TheoCorpus yet.")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Read the full text at the source/ }).getAttribute("href"))
      .toBe("https://example.org/libertas");
    expect(screen.queryByText("This document couldn't be loaded.")).toBeNull();
    expect(api.putReadingProgress).not.toHaveBeenCalled();
  });

  it("shows the same notice on the document overview", async () => {
    const { ReaderRestrictedError } = await import("@/lib/api");
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockRejectedValue(new ReaderRestrictedError(null));

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByText("The full text of this document isn't available on TheoCorpus yet.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Read the full text/ })).toBeNull();
  });
});

describe("retired anchors (corpus cleanup 2.4a)", () => {
  it("sends a #retired-<release> anchor back unchanged and finds its element by ID", async () => {
    const anchor = "c1/p2#retired-rel-1";
    navigation.params = new Map([["anchor", anchor], ["from", "saved"]]);
    const scrolled: string[] = [];
    const scrollIntoView = vi.fn(function (this: HTMLElement) { scrolled.push(this.id); });
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { value: scrollIntoView, configurable: true });
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string) => ({
      ...chapter(docId, "c1"),
      passages: [{ id: "p", anchor, chapter_key: "c1", chapter_label: "C1", content: "text" }],
      highlight_anchor: anchor,
    }));

    try {
      render(<DocumentReader docId="doc-a" />);

      await waitFor(() => expect(scrolled).toContain(`anchor-${anchor}`));
      expect(api.getReaderChapter.mock.calls[0][2]).toMatchObject({ anchor });
      // A CSS selector would choke on the `#` and `/`; getElementById does not.
      expect(() => document.querySelector(`#anchor-${anchor}`)).toThrow();
    } finally {
      delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });
});

describe("removed and moved documents (corpus cleanup 2.4b)", () => {
  const tombstone = {
    entity: "document" as const, rule: "", reason_code: "awaiting-permission",
    public_reason: "This translation is not available on TheoCorpus at present.",
    read_elsewhere_url: "https://www.papalencyclicals.net/greg16/g16mirar.htm",
    retired_at: "2026-12-01T00:00:00Z", title: "Mirari Vos", author: "Pope Gregory XVI",
  };

  it("shows the removal page for a 410, with where the text can still be read", async () => {
    const { ReaderRemovedError } = await import("@/lib/api");
    navigation.params = new Map([["anchor", "mirari-vos/1#retired-p4"], ["from", "saved"]]);
    api.getReaderChapter.mockRejectedValue(new ReaderRemovedError(tombstone));

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByText("Mirari Vos")).toBeTruthy();
    expect(screen.getByText("Pope Gregory XVI")).toBeTruthy();
    expect(screen.getByText("Not available on TheoCorpus")).toBeTruthy();
    expect(screen.getByText(tombstone.public_reason)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Read it at papalencyclicals.net/ }).getAttribute("href"))
      .toBe(tombstone.read_elsewhere_url);
    expect(screen.queryByText("This document couldn't be loaded.")).toBeNull();
    // The suffixed anchor went to the API unchanged.
    expect(api.getReaderChapter.mock.calls[0][2]).toMatchObject({ anchor: "mirari-vos/1#retired-p4" });
    expect(api.putReadingProgress).not.toHaveBeenCalled();
  });

  it("shows the removal page on the document overview", async () => {
    const { ReaderRemovedError } = await import("@/lib/api");
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockRejectedValue(new ReaderRemovedError(tombstone));

    render(<DocumentReader docId="doc-a" />);

    expect(await screen.findByText(tombstone.public_reason)).toBeTruthy();
    expect(screen.queryByText("This document overview couldn't be loaded.")).toBeNull();
  });

  it("replaces the URL with where a moved passage went, keeping from and returnKey", async () => {
    const { ReaderMovedError } = await import("@/lib/api");
    const returnKey = "22222222-2222-4222-8222-222222222222";
    navigation.params = new Map([["anchor", "old/1"], ["from", "saved"], ["returnKey", returnKey]]);
    api.getReaderChapter.mockRejectedValue(new ReaderMovedError({ kind: "split", document_id: "doc-b", anchor: "new/1" }));

    render(<DocumentReader docId="doc-a" />);

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith(
      `/reader/doc-b?from=saved&returnKey=${returnKey}&anchor=new%2F1`,
    ));
  });

  it("replaces the URL when the overview's document moved", async () => {
    const { ReaderMovedError } = await import("@/lib/api");
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockRejectedValue(new ReaderMovedError({ kind: "moved", document_id: "doc-b" }));

    render(<DocumentReader docId="doc-a" />);

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/reader/doc-b?from=library"));
  });

  it("opens the other document when the API followed a redirect into it", async () => {
    navigation.params = new Map([["anchor", "old/1"], ["from", "search"]]);
    api.getReaderChapter.mockImplementation(async () => ({
      ...chapter("doc-b", "c1"),
      highlight_anchor: "new/1",
      redirected_from: { document_id: "doc-a", anchor: "old/1" },
    }));

    render(<DocumentReader docId="doc-a" />);

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/reader/doc-b?from=search&anchor=new%2F1"));
  });

  it("highlights the new anchor when the redirect stays in the document", async () => {
    navigation.params = new Map([["anchor", "old/1"], ["from", "search"]]);
    const scrolled: string[] = [];
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      value: vi.fn(function (this: HTMLElement) { scrolled.push(this.id); }), configurable: true,
    });
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string) => ({
      ...chapter(docId, "c1"),
      passages: [{ id: "p", anchor: "new/1", chapter_key: "c1", chapter_label: "C1", content: "text" }],
      highlight_anchor: "new/1",
      redirected_from: { document_id: docId, anchor: "old/1" },
    }));

    try {
      render(<DocumentReader docId="doc-a" />);
      await waitFor(() => expect(scrolled).toContain("anchor-new/1"));
      expect(navigation.replace).not.toHaveBeenCalled();
    } finally {
      delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });
});

describe("corpus cleanup 2.4b: overview and later chapters", () => {
  it("keeps the overview's translation code when the API sends no facts", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockResolvedValue({
      document: { ...documentInfo("doc-a"), author: "Anon", year: 1990, translation: "WEB-C" },
      chapters: [{ chapter_key: "chapter-a", chapter_label: "Chapter A" }],
    });
    render(<DocumentReader docId="doc-a" />);
    expect(await screen.findByText("Anon · 1990 · WEB-C")).toBeTruthy();
  });

  it("names the translation in full when the API sends facts", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockResolvedValue({
      document: { ...documentInfo("doc-a"), author: "Anon", year: 1990, translation: "WEB-C", facts: { translation: "WEB-C" } },
      chapters: [{ chapter_key: "chapter-a", chapter_label: "Chapter A" }],
    });
    render(<DocumentReader docId="doc-a" />);
    expect(await screen.findByText("Anon · 1990 · World English Bible, Catholic Edition")).toBeTruthy();
  });

  it("says what a papal document is and how it was issued (issue #330)", async () => {
    navigation.params = new Map([["from", "library"]]);
    api.getToc.mockResolvedValue({
      document: {
        ...documentInfo("doc-a"), author: "Pope Pius IX", year: 1854,
        facts: { genre: "apostolic-constitution", form: "bull", translation: "Vatican English" },
      },
      chapters: [{ chapter_key: "chapter-a", chapter_label: "Chapter A" }],
    });
    render(<DocumentReader docId="doc-a" />);
    expect((await screen.findByTestId("document-kind")).textContent)
      .toBe("Apostolic constitution · issued as a bull");
  });

  it("shows the removal page when a later chapter was removed", async () => {
    const { ReaderRemovedError } = await import("@/lib/api");
    navigation.params = new Map([["chapter", "chapter-a"], ["from", "library"]]);
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => {
      if (options.chapter === "chapter-b") {
        throw new ReaderRemovedError({ entity: "passage", rule: "G", reason_code: "debris", public_reason: "A heading only.", retired_at: "" });
      }
      return chapter(docId, "chapter-a");
    });
    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));
    expect(await screen.findByText("A heading only.")).toBeTruthy();
  });

  it("opens the other document when a later chapter moved into it", async () => {
    navigation.params = new Map([["chapter", "chapter-a"], ["from", "library"]]);
    api.getReaderChapter.mockImplementation(async (_token: string, docId: string, options: { chapter?: string }) => (
      options.chapter === "chapter-b"
        ? { ...chapter("doc-b", "chapter-z"), redirected_from: { document_id: docId, chapter_key: "chapter-b" } }
        : chapter(docId, "chapter-a")
    ));
    render(<DocumentReader docId="doc-a" />);
    await screen.findByText("doc-a chapter-a");
    fireEvent.click(screen.getByRole("button", { name: "Jump B" }));
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/reader/doc-b?from=library&chapter=chapter-z"));
    expect(screen.queryByText("doc-b chapter-z")).toBeNull();
  });
});
