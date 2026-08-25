// @vitest-environment jsdom

import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchPage } from "./SearchPage";
import { SearchRestoreHttpError, type ChunkResult, type SearchStreamCallbacks } from "@/lib/api";

const testState = vi.hoisted(() => ({
  params: "restore=11111111-1111-4111-8111-111111111111",
  token: "token" as string | null,
  userId: "user-a" as string | null,
  searchKey: 0,
}));

const apiMocks = vi.hoisted(() => ({
  getSearchResults: vi.fn(),
  streamGuestSearch: vi.fn(),
  streamSearch: vi.fn(),
  updatePreferences: vi.fn().mockResolvedValue(undefined),
}));

const appMocks = vi.hoisted(() => ({
  setActiveSearchId: vi.fn(),
  setPendingSearch: vi.fn(),
  clearPendingSearch: vi.fn(),
  refreshSearches: vi.fn(),
}));

const navigationMocks = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
const animationMocks = vi.hoisted(() => ({ onFiltersReady: null as null | (() => void) }));
const guestGateMocks = vi.hoisted(() => ({
  searchCount: 0,
  requestSignup: vi.fn(),
  recordCompletedSearch: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => navigationMocks,
  useSearchParams: () => new URLSearchParams(testState.params),
}));

vi.mock("@/lib/trial", () => ({
  getGuestSessionToken: () => "guest-session-token-with-at-least-32-chars",
  GUEST_SEARCH_LIMIT: 2,
}));

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({
    token: testState.token,
    userId: testState.userId,
    preferences: { default_collections: ["bible"], preferred_translation: "CPDV", default_quota: 4 },
    searchKey: testState.searchKey,
    searches: [{
      id: "11111111-1111-4111-8111-111111111111",
      query: "Restored query",
      filters: { collections: ["bible"] },
      result_count: 0,
      created_at: "2026-08-08T00:00:00Z",
    }],
    setActiveSearchId: appMocks.setActiveSearchId,
    setPendingSearch: appMocks.setPendingSearch,
    clearPendingSearch: appMocks.clearPendingSearch,
    refreshSearches: appMocks.refreshSearches,
  }),
}));

vi.mock("@/components/layout/guestGate", () => ({
  useGuestGate: () => guestGateMocks,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getSearchResults: apiMocks.getSearchResults,
    streamGuestSearch: apiMocks.streamGuestSearch,
    streamSearch: apiMocks.streamSearch,
    updatePreferences: apiMocks.updatePreferences,
  };
});

vi.mock("./BottomBar", () => ({
  BottomBar: ({ isSearchActive, activeCollections, searchValue, onSearchChange, onSearch, onToggleVisible }: {
    isSearchActive: boolean;
    activeCollections: string[];
    searchValue: string;
    onSearchChange: (value: string) => void;
    onSearch: () => void;
    onToggleVisible: (collection: string) => void;
  }) => (
    <div data-testid="bottom-bar" data-active={String(isSearchActive)} data-collections={activeCollections.join(",")}>
      <input aria-label="Search passages" value={searchValue} onChange={(event) => onSearchChange(event.target.value)} />
      <button onClick={onSearch}>Search</button>
      <button onClick={() => onToggleVisible("bible")}>Toggle Bible visibility</button>
    </div>
  ),
}));
vi.mock("./EmptyState", () => ({ EmptyState: () => <div>Empty search</div> }));
vi.mock("./SearchResults", () => ({
  SearchResults: ({ results, loading, isRestoring, onExploreMore }: {
    results: Array<{ content: string; explanation: string | null }>;
    loading: boolean;
    isRestoring: boolean;
    onExploreMore: (content: string, label: string) => void;
  }) => (
    <div>
      {loading && isRestoring ? "Restoring" : "Restored results"}
      {results.map((result) => <div key={result.content}>{result.content} — {result.explanation}</div>)}
      {!loading && <button onClick={() => onExploreMore("A restored passage", "CCC 1000")}>Query More Like This</button>}
    </div>
  ),
}));
vi.mock("./LoadingAnimation", () => ({
  LoadingAnimation: ({ isQueryDone, onFiltersReady, onReadyToShow, onFadeComplete }: {
    isQueryDone: boolean;
    onFiltersReady: () => void;
    onReadyToShow: () => void;
    onFadeComplete: () => void;
  }) => {
    animationMocks.onFiltersReady = onFiltersReady;
    return (
      <div data-testid="loading-animation" data-query-done={String(isQueryDone)}>
        <button onClick={onFiltersReady}>Animation filters ready</button>
        <button onClick={onReadyToShow}>Animation ready</button>
        <button onClick={onFadeComplete}>Animation faded</button>
      </div>
    );
  },
}));

const restored = (query: string) => ({
  search_id: "11111111-1111-4111-8111-111111111111",
  query,
  filters: { collections: ["bible"], translation: "WEB-C", quota: 5 },
  results: [],
  restore_status: "complete" as const,
  expected_result_count: 0,
});

const streamedPassage: ChunkResult = {
  chunk_id: "passage-1",
  content: "Grace perfects nature.",
  source: {
    collection: "bible",
    document_title: "Romans",
    author: null,
    reference: "Romans 5:20",
    document_id: "document-1",
    position: 1,
  },
  reranker_score: 0.9,
  explanation: null,
  context: null,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  apiMocks.getSearchResults.mockReset();
  apiMocks.streamGuestSearch.mockReset();
  apiMocks.streamSearch.mockReset();
  apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
    callbacks.onDone("22222222-2222-4222-8222-222222222222", 1, "success", { bible: "results" }, true);
  });
  testState.params = "restore=11111111-1111-4111-8111-111111111111";
  testState.token = "token";
  testState.userId = "user-a";
  testState.searchKey = 0;
  guestGateMocks.searchCount = 0;
  animationMocks.onFiltersReady = null;
  sessionStorage.clear();
});

describe("SearchPage restore lifecycle", () => {
  it("survives Strict Mode effect replay instead of remaining on the skeleton", async () => {
    apiMocks.getSearchResults.mockResolvedValue(restored("Strict restore"));

    render(<StrictMode><SearchPage /></StrictMode>);

    expect(await screen.findByText("Strict restore")).toBeTruthy();
    expect(screen.queryByText("Restoring")).toBeNull();
  });

  it("settles restore state when the restore parameter disappears", async () => {
    apiMocks.getSearchResults.mockImplementation((_token, _id, signal: AbortSignal) =>
      new Promise((_resolve, reject) => signal.addEventListener(
        "abort",
        () => reject(new DOMException("Aborted", "AbortError")),
        { once: true },
      )),
    );
    const view = render(<SearchPage />);
    expect(await screen.findByText("Restoring")).toBeTruthy();

    testState.params = "";
    view.rerender(<SearchPage />);

    expect(await screen.findByText("Empty search")).toBeTruthy();
    expect(screen.queryByText("Restoring")).toBeNull();
  });

  it("clears the prior search UI when a replacement restore fails", async () => {
    apiMocks.getSearchResults
      .mockResolvedValueOnce(restored("First restored query"))
      .mockRejectedValueOnce(new SearchRestoreHttpError(503, "Temporarily unavailable"));
    const view = render(<SearchPage />);
    expect(await screen.findByText("First restored query")).toBeTruthy();

    testState.params = "restore=22222222-2222-4222-8222-222222222222";
    view.rerender(<SearchPage />);

    expect(await screen.findByText("This saved search couldn’t be loaded")).toBeTruthy();
    expect(screen.queryByText("First restored query")).toBeNull();
    expect(screen.getByTestId("bottom-bar").dataset.active).toBe("false");
    expect(appMocks.setActiveSearchId).toHaveBeenLastCalledWith(null);
  });

  it("retries a temporary restore failure", async () => {
    apiMocks.getSearchResults
      .mockRejectedValueOnce(new SearchRestoreHttpError(504, "Timed out"))
      .mockResolvedValueOnce(restored("Recovered query"));
    render(<SearchPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Retry saved search" }));

    expect(await screen.findByText("Recovered query")).toBeTruthy();
    await waitFor(() => expect(apiMocks.getSearchResults).toHaveBeenCalledTimes(2));
  });

  it("rejects a malformed saved-search route without calling the API", async () => {
    testState.params = "restore=not-a-search-id";
    render(<SearchPage />);

    expect(await screen.findByText("Saved search not found")).toBeTruthy();
    expect(apiMocks.getSearchResults).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Retry saved search" })).toBeNull();
  });

  it("keeps available Passages usable when part of a saved search is unavailable", async () => {
    apiMocks.getSearchResults.mockResolvedValue({
      ...restored("Partially restored query"),
      results: [streamedPassage],
      restore_status: "results_unavailable",
      expected_result_count: 3,
    });
    render(<SearchPage />);

    expect(await screen.findByText(/Grace perfects nature/)).toBeTruthy();
    expect(screen.getByText(
      "This saved search originally had 3 Passages, but only 1 remain available.",
    )).toBeTruthy();
  });

  it("preserves a completed restore across same-user access-token rotation", async () => {
    apiMocks.getSearchResults.mockResolvedValue(restored("Stable restored query"));
    const view = render(<SearchPage />);
    expect(await screen.findByText("Stable restored query")).toBeTruthy();

    testState.token = "refreshed-token";
    view.rerender(<SearchPage />);

    expect(screen.getByText("Stable restored query")).toBeTruthy();
    expect(screen.queryByText("Restoring")).toBeNull();
    expect(apiMocks.getSearchResults).toHaveBeenCalledTimes(1);
  });

  it("reauthorizes an in-flight restore after same-user access-token rotation", async () => {
    apiMocks.getSearchResults
      .mockImplementationOnce((_token, _id, signal: AbortSignal) =>
        new Promise((_resolve, reject) => signal.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        )),
      )
      .mockResolvedValueOnce(restored("Restored with rotated token"));
    const view = render(<SearchPage />);
    await waitFor(() => expect(apiMocks.getSearchResults).toHaveBeenCalledOnce());

    testState.token = "refreshed-token";
    view.rerender(<SearchPage />);

    expect(await screen.findByText("Restored with rotated token")).toBeTruthy();
    expect(apiMocks.getSearchResults.mock.calls.map((call) => call[0])).toEqual([
      "token",
      "refreshed-token",
    ]);
  });

  it("clears and reauthorizes a restore when the authenticated user changes", async () => {
    apiMocks.getSearchResults
      .mockResolvedValueOnce(restored("First user's query"))
      .mockResolvedValueOnce(restored("Second user's query"));
    const view = render(<SearchPage />);
    expect(await screen.findByText("First user's query")).toBeTruthy();

    testState.token = "different-user-token";
    testState.userId = "user-b";
    view.rerender(<SearchPage />);

    expect(await screen.findByText("Second user's query")).toBeTruthy();
    expect(screen.queryByText("First user's query")).toBeNull();
    expect(apiMocks.getSearchResults).toHaveBeenCalledTimes(2);
  });

  it("does not reuse a completed restore after logout", async () => {
    apiMocks.getSearchResults.mockResolvedValue(restored("Private restored query"));
    const view = render(<SearchPage />);
    expect(await screen.findByText("Private restored query")).toBeTruthy();

    testState.token = null;
    testState.userId = null;
    view.rerender(<SearchPage />);

    expect(screen.queryByText("Private restored query")).toBeNull();
    expect(screen.getByText("Empty search")).toBeTruthy();
  });

  it("leaves restore mode before querying more like a restored result", async () => {
    apiMocks.getSearchResults.mockResolvedValue(restored("Restored query"));
    const view = render(<SearchPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Query More Like This" }));

    expect(navigationMocks.replace).toHaveBeenCalledWith("/search");
    testState.params = "";
    view.rerender(<SearchPage />);
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalled());
    expect(apiMocks.streamSearch.mock.calls[0][1]).toBe("A restored passage");
    expect(apiMocks.streamSearch.mock.calls[0][2]).toEqual({ collections: ["bible"], translation: "WEB-C" });
    expect(apiMocks.streamSearch.mock.calls[0][3]).toBe(5);
    expect(screen.getByTestId("bottom-bar").dataset.collections).toBe("bible");
  });

  it("submits a queued restored-result explore handoff only once", async () => {
    apiMocks.getSearchResults.mockResolvedValue(restored("Restored query"));
    const view = render(<SearchPage />);
    const queryMore = await screen.findByRole("button", { name: "Query More Like This" });

    fireEvent.click(queryMore);
    fireEvent.click(queryMore);
    expect(apiMocks.streamSearch).not.toHaveBeenCalled();

    testState.params = "";
    view.rerender(<SearchPage />);
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
  });

  it("discards a queued restored-result explore handoff when the user changes", async () => {
    apiMocks.getSearchResults.mockResolvedValue(restored("First user's restored query"));
    const view = render(<SearchPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Query More Like This" }));

    testState.token = "user-b-token";
    testState.userId = "user-b";
    view.rerender(<SearchPage />);
    await waitFor(() => expect(apiMocks.getSearchResults).toHaveBeenCalledTimes(2));
    testState.params = "";
    view.rerender(<SearchPage />);

    await waitFor(() => expect(screen.getByText("Empty search")).toBeTruthy());
    expect(apiMocks.streamSearch).not.toHaveBeenCalled();
  });

  it("discards a queued restored-result explore handoff when the search resets", async () => {
    apiMocks.getSearchResults.mockResolvedValue(restored("Restored query"));
    const view = render(<SearchPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Query More Like This" }));

    testState.searchKey += 1;
    view.rerender(<SearchPage />);
    testState.params = "";
    view.rerender(<SearchPage />);

    await waitFor(() => expect(screen.getByText("Empty search")).toBeTruthy());
    expect(apiMocks.streamSearch).not.toHaveBeenCalled();
  });

  it("submits one route-driven explore search during Strict Mode replay", async () => {
    testState.params = "explore=Grace%20perfects%20nature&exploreRef=ST%20I-II%2C%20q.%20109";
    render(<StrictMode><SearchPage /></StrictMode>);

    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    expect(apiMocks.streamSearch.mock.calls[0].slice(1, 4)).toEqual([
      "Grace perfects nature",
      { collections: ["bible"], translation: "CPDV" },
      4,
    ]);
    expect(navigationMocks.replace).toHaveBeenCalledWith("/search");
  });
});

describe("SearchPage animation-gated stream reveal", () => {
  it("discards a delayed explore submission when the user changes", async () => {
    testState.params = "";
    const view = render(<SearchPage />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Animation ready" }));
    fireEvent.click(await screen.findByRole("button", { name: "Query More Like This" }));

    testState.token = "user-b-token";
    testState.userId = "user-b";
    view.rerender(<SearchPage />);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });

    expect(apiMocks.streamSearch).toHaveBeenCalledOnce();
  });

  it("ignores a filters-ready milestone from a replaced animation", async () => {
    testState.params = "";
    const streamCallbacks: SearchStreamCallbacks[] = [];
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
      streamCallbacks.push(callbacks);
    });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "first" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    const staleFiltersReady = animationMocks.onFiltersReady!;

    act(() => streamCallbacks[0].onError("First search failed", "server_error", "retrieval"));
    fireEvent.click(await screen.findByRole("button", { name: "Retry search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("bottom-bar").dataset.active).toBe("false");

    act(() => staleFiltersReady());
    expect(screen.getByTestId("bottom-bar").dataset.active).toBe("false");

    act(() => animationMocks.onFiltersReady!());
    expect(screen.getByTestId("bottom-bar").dataset.active).toBe("true");
  });

  it("clears the authenticated pending History entry when a search fails", async () => {
    testState.params = "";
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
    });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    const placeholderEntry = appMocks.setPendingSearch.mock.calls.find((call) => call[1] === "New Search");
    const submittedEntry = appMocks.setPendingSearch.mock.calls.find((call) => call[1] === "grace");
    expect(submittedEntry?.[0]).toBe(placeholderEntry?.[0]);
    appMocks.clearPendingSearch.mockClear();

    act(() => streamCallbacks.onError("Retrieval failed", "retrieval_failed", "retrieval"));

    expect(await screen.findByText("Passage retrieval failed")).toBeTruthy();
    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
  });

  it("retries the frozen authenticated request with the current access token", async () => {
    testState.params = "";
    const streamCallbacks: SearchStreamCallbacks[] = [];
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
      streamCallbacks.push(callbacks);
    });
    const view = render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "original query" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    act(() => streamCallbacks[0].onError("Network unavailable", "network_error", "connection"));
    await screen.findByRole("button", { name: "Retry search" });

    testState.token = "rotated-token";
    view.rerender(<SearchPage />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "changed draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));

    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledTimes(2));
    expect(apiMocks.streamSearch.mock.calls[1].slice(0, 4)).toEqual([
      "rotated-token",
      "original query",
      { collections: ["bible"], translation: "CPDV" },
      4,
    ]);
  });

  it("aborts and clears the owning authenticated run when identity changes", async () => {
    testState.params = "";
    let streamSignal!: AbortSignal;
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, _callbacks, signal) => {
      streamSignal = signal!;
    });
    const view = render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    appMocks.clearPendingSearch.mockClear();

    testState.token = "different-user-token";
    testState.userId = "user-b";
    view.rerender(<SearchPage />);

    expect(streamSignal.aborted).toBe(true);
    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
    expect(screen.queryByTestId("loading-animation")).toBeNull();
  });

  it("cancels the authenticated runtime before starting a saved-search restore", async () => {
    testState.params = "";
    let streamSignal!: AbortSignal;
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, _callbacks, signal) => {
      streamSignal = signal!;
    });
    const view = render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    appMocks.clearPendingSearch.mockClear();

    apiMocks.getSearchResults.mockResolvedValue(restored("Restored after cancellation"));
    testState.params = "restore=11111111-1111-4111-8111-111111111111";
    view.rerender(<SearchPage />);

    expect(streamSignal.aborted).toBe(true);
    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
    expect(await screen.findByText("Restored after cancellation")).toBeTruthy();
  });

  it("clears a rate-limited authenticated run before presenting the modal", async () => {
    testState.params = "";
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
    });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    appMocks.clearPendingSearch.mockClear();

    act(() => streamCallbacks.onRateLimit(25, "per_minute"));

    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
    expect(await screen.findByRole("dialog", { name: "Search Limit Reached" })).toBeTruthy();
  });

  it("keeps a replacement pending entry when stale callbacks clean up the older run", async () => {
    testState.params = "";
    const streamCallbacks: SearchStreamCallbacks[] = [];
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
      streamCallbacks.push(callbacks);
    });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "first" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    appMocks.clearPendingSearch.mockClear();

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "second" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledTimes(2));
    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
    const firstEntry = appMocks.setPendingSearch.mock.calls.find((call) => call[1] === "first");
    const secondEntry = appMocks.setPendingSearch.mock.calls.find((call) => call[1] === "second");
    expect(secondEntry?.[0]).not.toBe(firstEntry?.[0]);

    act(() => streamCallbacks[0].onError("stale failure"));
    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
    act(() => streamCallbacks[1].onError("current failure"));
    expect(appMocks.clearPendingSearch).toHaveBeenCalledTimes(2);
  });

  it("clears pending History before refreshing and activates the persisted search", async () => {
    testState.params = "";
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
    });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    appMocks.clearPendingSearch.mockClear();
    appMocks.refreshSearches.mockClear();
    appMocks.setActiveSearchId.mockClear();

    act(() => streamCallbacks.onDone("persisted-search", 0, "no_candidates", {}, true));

    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
    expect(appMocks.refreshSearches).toHaveBeenCalledOnce();
    expect(appMocks.clearPendingSearch.mock.invocationCallOrder[0])
      .toBeLessThan(appMocks.refreshSearches.mock.invocationCallOrder[0]);
    await waitFor(() => expect(appMocks.setActiveSearchId).toHaveBeenCalledWith("persisted-search"));
  });

  it("cancels the owning run and creates a fresh placeholder on New Search", async () => {
    testState.params = "";
    let streamSignal!: AbortSignal;
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, _callbacks, signal) => {
      streamSignal = signal!;
    });
    const view = render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    const submittedEntry = appMocks.setPendingSearch.mock.calls.find((call) => call[1] === "grace");
    appMocks.clearPendingSearch.mockClear();

    testState.searchKey += 1;
    view.rerender(<SearchPage />);

    await waitFor(() => expect(streamSignal.aborted).toBe(true));
    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
    const newestPlaceholder = appMocks.setPendingSearch.mock.calls.at(-1);
    expect(newestPlaceholder?.[1]).toBe("New Search");
    expect(newestPlaceholder?.[0]).not.toBe(submittedEntry?.[0]);
  });

  it("clears the owning pending entry when the page is disposed", async () => {
    testState.params = "";
    let streamSignal!: AbortSignal;
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, _callbacks, signal) => {
      streamSignal = signal!;
    });
    const view = render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    appMocks.clearPendingSearch.mockClear();

    view.unmount();

    await waitFor(() => expect(streamSignal.aborted).toBe(true));
    expect(appMocks.clearPendingSearch).toHaveBeenCalledOnce();
  });

  it("does not let a disposed page clear the next page's pending History entry", async () => {
    testState.params = "";
    const firstPage = render(<SearchPage />);
    await waitFor(() => expect(appMocks.setPendingSearch).toHaveBeenCalledOnce());

    firstPage.unmount();
    render(<SearchPage />);
    await waitFor(() => expect(appMocks.setPendingSearch).toHaveBeenCalledTimes(2));
    const replacementOrder = appMocks.setPendingSearch.mock.invocationCallOrder[1];

    await act(async () => { await Promise.resolve(); });

    const lateClears = appMocks.clearPendingSearch.mock.invocationCallOrder
      .filter((order) => order > replacementOrder);
    expect(lateClears).toEqual([]);
  });

  it("buffers fast authenticated completion until reveal and keeps the overlay through its fade", async () => {
    testState.params = "";
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
      callbacks.onChunk(streamedPassage);
      callbacks.onExplanationDelta(streamedPassage.chunk_id, "Before reveal.");
      callbacks.onDone("search-1", 1, "success", { bible: "results" }, true);
    });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    expect(screen.getByTestId("loading-animation").dataset.queryDone).toBe("true");
    expect(screen.queryByText(/Grace perfects nature/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Animation ready" }));
    expect(await screen.findByText("Grace perfects nature. — Before reveal.")).toBeTruthy();
    expect(screen.getByTestId("loading-animation")).toBeTruthy();
    act(() => streamCallbacks.onExplanationDelta(streamedPassage.chunk_id, " After reveal."));
    expect(await screen.findByText("Grace perfects nature. — Before reveal. After reveal.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Animation faded" }));
    expect(screen.queryByTestId("loading-animation")).toBeNull();
  });

  it("keeps unpersisted authenticated Passages usable with the History warning", async () => {
    testState.params = "";
    apiMocks.streamSearch.mockImplementation(async (_token, _query, _filters, _quota, callbacks) => {
      callbacks.onChunk(streamedPassage);
      callbacks.onDone(null, 1, "degraded", { bible: "results_degraded" }, false);
    });
    render(<SearchPage />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamSearch).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Animation ready" }));

    expect(await screen.findByText(/Grace perfects nature/)).toBeTruthy();
    expect(screen.getByText("Results are available now, but search history could not be saved. They will not be restorable after you leave this page.")).toBeTruthy();
  });

  it("buffers guest results-ready output until reveal and keeps the overlay through its fade", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
      callbacks.onChunk(streamedPassage);
      callbacks.onExplanationDelta(streamedPassage.chunk_id, "Before reveal.");
      callbacks.onResultsReady?.(1);
    });
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    expect(screen.getByTestId("loading-animation").dataset.queryDone).toBe("true");
    expect(screen.queryByText(/Grace perfects nature/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Animation ready" }));
    expect(await screen.findByText("Grace perfects nature. — Before reveal.")).toBeTruthy();
    expect(screen.getByTestId("loading-animation")).toBeTruthy();
    expect(JSON.parse(sessionStorage.getItem("theocorpus-guest-current-results") ?? "null"))
      .toMatchObject({ query: "grace", passages: [{ explanation: "Before reveal." }] });

    act(() => streamCallbacks.onExplanationDelta(streamedPassage.chunk_id, " After reveal."));
    expect(await screen.findByText("Grace perfects nature. — Before reveal. After reveal.")).toBeTruthy();
    expect(JSON.parse(sessionStorage.getItem("theocorpus-guest-current-results") ?? "null"))
      .toMatchObject({ passages: [{ explanation: "Before reveal. After reveal." }] });

    fireEvent.click(screen.getByRole("button", { name: "Animation faded" }));
    expect(screen.queryByTestId("loading-animation")).toBeNull();
  });

  it("keeps revealed guest Passages when final completion fails", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
      callbacks.onChunk(streamedPassage);
      callbacks.onResultsReady?.(1);
    });
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Animation ready" }));
    expect(await screen.findByText(/Grace perfects nature/)).toBeTruthy();

    act(() => streamCallbacks.onError("Transfer finalization failed", "transfer_failed", "transfer"));

    expect(screen.getByText(/Grace perfects nature/)).toBeTruthy();
    expect(screen.queryByText("Passage retrieval failed")).toBeNull();
    expect(screen.getByText("Transfer finalization failed")).toBeTruthy();
  });

  it("keeps revealed guest Passages visible under a late rate-limit modal", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
      callbacks.onChunk(streamedPassage);
      callbacks.onResultsReady?.(1);
    });
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Animation ready" }));
    act(() => streamCallbacks.onRateLimit(20, "per_minute"));

    expect(screen.getByText(/Grace perfects nature/)).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "Search Limit Reached" })).toBeTruthy();
  });

  it("records one guest trial use at results readiness and not again at done", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
    });
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    expect(apiMocks.streamGuestSearch.mock.calls[0].slice(0, 4)).toEqual([
      "guest-session-token-with-at-least-32-chars",
      "grace",
      {
        collections: ["bible", "catechism", "church-fathers", "summa", "councils", "encyclicals"],
        translation: "CPDV",
      },
      3,
    ]);

    act(() => streamCallbacks.onResultsReady?.(1));
    expect(guestGateMocks.recordCompletedSearch).toHaveBeenCalledOnce();
    act(() => streamCallbacks.onDone(null, 1, "success", { bible: "results" }, true));
    expect(guestGateMocks.recordCompletedSearch).toHaveBeenCalledOnce();
  });

  it("opens signup when the server reports an exhausted guest trial", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
    });
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    act(() => streamCallbacks.onError("trial_exhausted", "rate_limit", "rate_limit"));

    expect(guestGateMocks.requestSignup).toHaveBeenCalledWith("limit");
    expect(screen.queryByTestId("loading-animation")).toBeNull();
    expect(screen.getByText("Empty search")).toBeTruthy();
  });

  it("rejects an exhausted guest trial before opening a stream", () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    guestGateMocks.searchCount = 2;
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(apiMocks.streamGuestSearch).not.toHaveBeenCalled();
    expect(guestGateMocks.requestSignup).toHaveBeenCalledWith("limit");
  });

  it("keeps revealed guest results when a later submit reaches the local trial limit", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    let streamCallbacks!: SearchStreamCallbacks;
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, callbacks) => {
      streamCallbacks = callbacks;
      callbacks.onChunk(streamedPassage);
      callbacks.onResultsReady?.(1);
    });
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Animation ready" }));
    expect(await screen.findByText(/Grace perfects nature/)).toBeTruthy();

    guestGateMocks.searchCount = 2;
    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "another" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce();
    expect(guestGateMocks.requestSignup).toHaveBeenCalledWith("limit");
    expect(screen.getByText(/Grace perfects nature/)).toBeTruthy();
    expect(streamCallbacks).toBeTruthy();
  });

  it("ignores guest callbacks after a replacement search takes ownership", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    const callbacks: SearchStreamCallbacks[] = [];
    const signals: AbortSignal[] = [];
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, streamCallbacks, signal) => {
      callbacks.push(streamCallbacks);
      signals.push(signal!);
    });
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "first" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "second" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledTimes(2));

    expect(signals[0].aborted).toBe(true);
    act(() => callbacks[0].onError("stale failure", "server_error", "retrieval"));
    expect(screen.queryByText("Passage retrieval failed")).toBeNull();
    act(() => callbacks[1].onError("current failure", "server_error", "retrieval"));
    expect(screen.getByText("Passage retrieval failed")).toBeTruthy();
  });

  it("retries the frozen guest request after a rate limit", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    const callbacks: SearchStreamCallbacks[] = [];
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, streamCallbacks) => {
      callbacks.push(streamCallbacks);
    });
    render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "original" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    act(() => callbacks[0].onRateLimit(5, "per_minute"));
    expect(await screen.findByRole("dialog", { name: "Search Limit Reached" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));

    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledTimes(2));
    expect(apiMocks.streamGuestSearch.mock.calls[1][1]).toBe("original");
  });

  it("aborts the guest stream when the page is disposed", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    let signal!: AbortSignal;
    apiMocks.streamGuestSearch.mockImplementation(async (_session, _query, _filters, _quota, _callbacks, streamSignal) => {
      signal = streamSignal!;
    });
    const view = render(<SearchPage isGuest />);

    fireEvent.change(screen.getByRole("textbox", { name: "Search passages" }), { target: { value: "grace" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(apiMocks.streamGuestSearch).toHaveBeenCalledOnce());
    view.unmount();

    await waitFor(() => expect(signal.aborted).toBe(true));
  });

  it("restores, saves, and clears the compatible guest Reader snapshot", async () => {
    testState.params = "";
    testState.token = null;
    testState.userId = null;
    sessionStorage.setItem("theocorpus-guest-current-results", JSON.stringify({
      savedAt: Date.now(),
      query: "restored guest query",
      results: [streamedPassage],
      searchId: "guest-search",
      collections: ["bible"],
      translation: "CPDV",
      quota: 3,
      visibleCollections: ["bible"],
      outcome: "success",
      collectionOutcomes: { bible: "results" },
    }));
    const view = render(<SearchPage isGuest />);

    expect(screen.getByText("restored guest query")).toBeTruthy();
    expect(screen.getByText(/Grace perfects nature/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Toggle Bible visibility" }));
    expect(JSON.parse(sessionStorage.getItem("theocorpus-guest-current-results") ?? "null"))
      .toMatchObject({ visibleCollections: [] });

    testState.searchKey += 1;
    view.rerender(<SearchPage isGuest />);
    await waitFor(() => expect(sessionStorage.getItem("theocorpus-guest-current-results")).toBeNull());
    expect(screen.getByText("Empty search")).toBeTruthy();
  });
});
