// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SearchHistoryPage, SearchSummaryV2 } from "@/lib/api";
import { __resetClientCachesForTests } from "@/lib/client-cache";
import { HistoryPage } from "./HistoryPage";

const api = vi.hoisted(() => ({
  getSearchHistoryPage: vi.fn(),
  getSearchResults: vi.fn(),
  deleteSearch: vi.fn(),
}));
const shell = vi.hoisted(() => ({
  value: {} as Record<string, unknown>,
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  ...api,
}));
vi.mock("@/components/layout/AppShell", () => ({ useAppContext: () => shell.value }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/analytics", () => ({ trackHistoryRestored: vi.fn(), trackSearchDeleted: vi.fn() }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const HOUR_AGO = new Date(Date.now() - 60 * 60 * 1000).toISOString();
const MINUTE_AGO = Date.now() - 60_000;

function summary(id: string, createdAt = HOUR_AGO): SearchSummaryV2 {
  return { id, query: `query ${id}`, filters: null, result_count: 3, created_at: createdAt };
}

function page(ids: string[], cursor: string | null = null): SearchHistoryPage {
  return { searches: ids.map((id) => summary(id)), next_cursor: cursor };
}

function context(overrides: Record<string, unknown> = {}) {
  return {
    token: "token",
    pendingSearch: null,
    activeSearchId: null,
    removeSearch: vi.fn(),
    newSearch: vi.fn(),
    searches: [],
    searchHistoryCursor: null,
    searchHistoryLoadedAt: null,
    ...overrides,
  };
}

function hoverCapable(matches: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
}

function row(id: string) {
  return screen.getByRole("link", { name: `query ${id}` });
}

beforeEach(() => {
  __resetClientCachesForTests();
  shell.value = context();
  api.getSearchHistoryPage.mockReset();
  api.getSearchHistoryPage.mockResolvedValue(page(["s1", "s2"], "cursor-1"));
  api.getSearchResults.mockReset();
  api.getSearchResults.mockImplementation(async (_token: string, searchId: string) => ({ search_id: searchId, query: searchId, results: [] }));
  api.deleteSearch.mockReset();
  api.deleteSearch.mockResolvedValue(undefined);
  hoverCapable(true);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("HistoryPage loading", () => {
  it("shows the skeleton and loads the first page when AppShell has none yet", async () => {
    render(<HistoryPage />);

    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(await screen.findByRole("link", { name: "query s1" })).toBeTruthy();
    expect(api.getSearchHistoryPage).toHaveBeenCalledTimes(1);
  });

  it("shows AppShell's list at once and refreshes it in the background", async () => {
    const refresh = deferred<SearchHistoryPage>();
    api.getSearchHistoryPage.mockReturnValue(refresh.promise);
    shell.value = context({ searches: [summary("old")], searchHistoryCursor: "cursor-old", searchHistoryLoadedAt: MINUTE_AGO });

    render(<HistoryPage />);

    expect(screen.getByRole("searchbox")).toBeTruthy();
    expect(row("old")).toBeTruthy();
    expect(api.getSearchHistoryPage).toHaveBeenCalledTimes(1);

    await act(async () => { refresh.resolve(page(["new", "old"], "cursor-2")); });
    expect(row("new")).toBeTruthy();
  });

  it("does not repeat AppShell's request when its list is moments old", async () => {
    shell.value = context({ searches: [summary("old")], searchHistoryCursor: "cursor-old", searchHistoryLoadedAt: Date.now() });

    render(<HistoryPage />);
    await act(async () => { await Promise.resolve(); });

    expect(row("old")).toBeTruthy();
    expect(api.getSearchHistoryPage).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Load older searches" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("refreshes a seed AppShell is still reloading, however recent", async () => {
    shell.value = context({ searches: [summary("old")], searchHistoryLoadedAt: 0 });

    render(<HistoryPage />);
    expect(row("old")).toBeTruthy();
    await act(async () => { await Promise.resolve(); });

    expect(api.getSearchHistoryPage).toHaveBeenCalledTimes(1);
    expect(row("s1")).toBeTruthy();
  });

  it("does not bring back a search deleted while the refresh was in flight", async () => {
    const refresh = deferred<SearchHistoryPage>();
    api.getSearchHistoryPage.mockReturnValue(refresh.promise);
    shell.value = context({ searches: [summary("old"), summary("keep")], searchHistoryLoadedAt: MINUTE_AGO });
    render(<HistoryPage />);

    fireEvent.click(screen.getByRole("button", { name: "Show delete option for query old" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete search: query old" }));
    await waitFor(() => expect(api.deleteSearch).toHaveBeenCalledWith("token", "old"));
    await act(async () => { refresh.resolve(page(["old", "keep"])); });

    expect(screen.queryByRole("link", { name: "query old" })).toBeNull();
    expect(row("keep")).toBeTruthy();
  });

  it("keeps the seeded list when the background refresh fails", async () => {
    api.getSearchHistoryPage.mockRejectedValue(new Error("offline"));
    shell.value = context({ searches: [summary("old")], searchHistoryLoadedAt: MINUTE_AGO });

    render(<HistoryPage />);
    await act(async () => { await Promise.resolve(); });

    expect(row("old")).toBeTruthy();
    expect(screen.queryByText("Your history couldn't be loaded.")).toBeNull();
  });

  it("continues pagination from the refreshed cursor, not before the refresh lands", async () => {
    const refresh = deferred<SearchHistoryPage>();
    api.getSearchHistoryPage.mockReturnValueOnce(refresh.promise).mockResolvedValueOnce(page(["older"]));
    shell.value = context({ searches: [summary("old")], searchHistoryCursor: "cursor-old", searchHistoryLoadedAt: MINUTE_AGO });

    render(<HistoryPage />);
    const loadMore = screen.getByRole("button", { name: "Load older searches" }) as HTMLButtonElement;
    expect(loadMore.disabled).toBe(true);

    await act(async () => { refresh.resolve(page(["new", "old"], "cursor-2")); });
    fireEvent.click(screen.getByRole("button", { name: "Load older searches" }));

    expect(await screen.findByRole("link", { name: "query older" })).toBeTruthy();
    expect(api.getSearchHistoryPage).toHaveBeenLastCalledWith("token", { cursor: "cursor-2", query: undefined });
  });

  it("does not use the seed for a filtered view", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const filtered = deferred<SearchHistoryPage>();
    shell.value = context({ searches: [summary("old")], searchHistoryLoadedAt: MINUTE_AGO });
    render(<HistoryPage />);
    await act(async () => { await Promise.resolve(); });
    api.getSearchHistoryPage.mockReturnValueOnce(filtered.promise);

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "grace" } });
    await act(async () => { vi.advanceTimersByTime(250); });

    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(api.getSearchHistoryPage).toHaveBeenLastCalledWith("token", { query: "grace" });
    await act(async () => { filtered.resolve(page(["match"])); });
    expect(row("match")).toBeTruthy();
  });

  it("does not reload when the access token refreshes", async () => {
    const view = render(<HistoryPage />);
    await screen.findByRole("link", { name: "query s1" });

    shell.value = context({ token: "refreshed-token" });
    view.rerender(<HistoryPage />);
    await act(async () => { await Promise.resolve(); });

    expect(api.getSearchHistoryPage).toHaveBeenCalledTimes(1);
    expect(row("s1")).toBeTruthy();
  });
});

describe("HistoryPage restore prefetch", () => {
  async function renderSeeded(searches: SearchSummaryV2[], overrides: Record<string, unknown> = {}) {
    api.getSearchHistoryPage.mockResolvedValue({ searches, next_cursor: null });
    shell.value = context({ searches, searchHistoryLoadedAt: MINUTE_AGO, ...overrides });
    render(<HistoryPage />);
    await act(async () => { await Promise.resolve(); });
    vi.useFakeTimers();
  }

  it("warms a row's results after the pointer rests on it", async () => {
    await renderSeeded([summary("s1")]);

    fireEvent.pointerEnter(row("s1"), { pointerType: "mouse" });
    act(() => { vi.advanceTimersByTime(149); });
    expect(api.getSearchResults).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1); });

    expect(api.getSearchResults).toHaveBeenCalledWith("token", "s1", expect.any(AbortSignal), 30_000);
  });

  it("warms nothing when the pointer only passes over", async () => {
    await renderSeeded([summary("s1")]);

    fireEvent.pointerEnter(row("s1"), { pointerType: "mouse" });
    act(() => { vi.advanceTimersByTime(100); });
    fireEvent.pointerLeave(row("s1"), { pointerType: "mouse" });
    act(() => { vi.advanceTimersByTime(500); });

    expect(api.getSearchResults).not.toHaveBeenCalled();
  });

  it("warms a row that keyboard focus rests on", async () => {
    const matches = Element.prototype.matches;
    vi.spyOn(Element.prototype, "matches").mockImplementation(function (this: Element, selector: string) {
      return selector === ":focus-visible" ? true : matches.call(this, selector);
    });
    await renderSeeded([summary("s1"), summary("s2")]);

    act(() => { row("s1").focus(); });
    act(() => { vi.advanceTimersByTime(50); });
    act(() => { row("s2").focus(); });
    act(() => { vi.advanceTimersByTime(150); });

    expect(api.getSearchResults.mock.calls.map((call) => call[1])).toEqual(["s2"]);
  });

  it("does not warm a row that receives focus without the keyboard", async () => {
    await renderSeeded([summary("s1")]);

    act(() => { row("s1").focus(); });
    act(() => { vi.advanceTimersByTime(500); });

    expect(api.getSearchResults).not.toHaveBeenCalled();
  });

  it("never prefetches on a device without hover", async () => {
    hoverCapable(false);
    await renderSeeded([summary("s1")]);

    fireEvent.pointerEnter(row("s1"), { pointerType: "mouse" });
    act(() => { row("s1").focus(); });
    act(() => { vi.advanceTimersByTime(500); });

    expect(api.getSearchResults).not.toHaveBeenCalled();
  });

  it("ignores touch pointers", async () => {
    await renderSeeded([summary("s1")]);

    fireEvent.pointerEnter(row("s1"), { pointerType: "touch" });
    act(() => { vi.advanceTimersByTime(500); });

    expect(api.getSearchResults).not.toHaveBeenCalled();
  });

  it("skips the active search, the one in progress, and searches under a minute old", async () => {
    const recent = summary("recent", new Date(Date.now() - 30_000).toISOString());
    await renderSeeded([summary("active"), summary("pending"), recent], {
      activeSearchId: "active",
      pendingSearch: { id: "pending", query: "query pending" },
    });

    for (const id of ["active", "pending", "recent"]) {
      fireEvent.pointerEnter(row(id), { pointerType: "mouse" });
      act(() => { vi.advanceTimersByTime(200); });
    }

    expect(api.getSearchResults).not.toHaveBeenCalled();
  });

  it("keeps one prefetch in flight, cancelling the previous row's", async () => {
    const signals: AbortSignal[] = [];
    api.getSearchResults.mockImplementation((_token: string, _id: string, signal: AbortSignal) => {
      signals.push(signal);
      return new Promise(() => {});
    });
    await renderSeeded([summary("s1"), summary("s2")]);

    fireEvent.pointerEnter(row("s1"), { pointerType: "mouse" });
    act(() => { vi.advanceTimersByTime(150); });
    fireEvent.pointerLeave(row("s1"), { pointerType: "mouse" });
    expect(signals[0].aborted).toBe(false);
    fireEvent.pointerEnter(row("s2"), { pointerType: "mouse" });
    act(() => { vi.advanceTimersByTime(150); });
    await act(async () => { await vi.runOnlyPendingTimersAsync(); });

    expect(signals).toHaveLength(2);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });

  it("releases a prefetch in flight when the page closes", async () => {
    const signals: AbortSignal[] = [];
    api.getSearchResults.mockImplementation((_token: string, _id: string, signal: AbortSignal) => {
      signals.push(signal);
      return new Promise(() => {});
    });
    await renderSeeded([summary("s1")]);
    fireEvent.pointerEnter(row("s1"), { pointerType: "mouse" });
    act(() => { vi.advanceTimersByTime(150); });

    cleanup();
    await act(async () => { await vi.runOnlyPendingTimersAsync(); });

    expect(signals[0].aborted).toBe(true);
  });

  it("forgets a prefetched search when it is deleted", async () => {
    await renderSeeded([summary("s1")]);
    fireEvent.pointerEnter(row("s1"), { pointerType: "mouse" });
    act(() => { vi.advanceTimersByTime(150); });
    await act(async () => { await Promise.resolve(); });
    vi.useRealTimers();

    fireEvent.click(screen.getByRole("button", { name: "Show delete option for query s1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete search: query s1" }));
    await waitFor(() => expect(api.deleteSearch).toHaveBeenCalledWith("token", "s1"));

    const { loadSavedSearchResults } = await import("@/lib/saved-search-cache");
    await loadSavedSearchResults("token", "s1");
    expect(api.getSearchResults).toHaveBeenCalledTimes(2);
  });
});
