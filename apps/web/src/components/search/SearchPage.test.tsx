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
    searchKey: 0,
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
  BottomBar: ({ isSearchActive, activeCollections, searchValue, onSearchChange, onSearch }: {
    isSearchActive: boolean;
    activeCollections: string[];
    searchValue: string;
    onSearchChange: (value: string) => void;
    onSearch: () => void;
  }) => (
    <div data-testid="bottom-bar" data-active={String(isSearchActive)} data-collections={activeCollections.join(",")}>
      <input aria-label="Search passages" value={searchValue} onChange={(event) => onSearchChange(event.target.value)} />
      <button onClick={onSearch}>Search</button>
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
  LoadingAnimation: ({ isQueryDone, onReadyToShow, onFadeComplete }: {
    isQueryDone: boolean;
    onReadyToShow: () => void;
    onFadeComplete: () => void;
  }) => (
    <div data-testid="loading-animation" data-query-done={String(isQueryDone)}>
      <button onClick={onReadyToShow}>Animation ready</button>
      <button onClick={onFadeComplete}>Animation faded</button>
    </div>
  ),
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
});

describe("SearchPage animation-gated stream reveal", () => {
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

    act(() => streamCallbacks.onExplanationDelta(streamedPassage.chunk_id, " After reveal."));
    expect(await screen.findByText("Grace perfects nature. — Before reveal. After reveal.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Animation faded" }));
    expect(screen.queryByTestId("loading-animation")).toBeNull();
  });
});
