import { afterEach, describe, expect, it, vi } from "vitest";

import { claimGuestSession, deleteSearch, getBookmarks, getReadingProgress, getSearchHistoryPage, getSearchResults, GuestClaimHttpError, invalidateBookmarksCache, putReadingProgress, removeBookmark, SearchRestoreHttpError, streamGuestSearch, streamSearch, submitProductFeedback, type Bookmark, type SearchStreamCallbacks } from "./api";

function callbacks() {
  return {
    onChunk: vi.fn(),
    onExplanationDelta: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
    onRateLimit: vi.fn(),
    onStatus: vi.fn(),
    onResultsReady: vi.fn(),
  } satisfies SearchStreamCallbacks;
}

function response(...events: unknown[]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n`).join("");
  return new Response(body, { status: 200 });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  invalidateBookmarksCache();
});

function bookmarkFixture(id: string): Bookmark {
  return {
    id,
    chunk_id: `chunk-${id}`,
    created_at: "2026-08-08T00:00:00Z",
    note: null,
    chunk: null,
  };
}

function jwtForSubject(subject: string, suffix: string): string {
  const payload = btoa(JSON.stringify({ sub: subject })).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `header.${payload}.${suffix}`;
}

function chunkEvent(context: unknown): unknown {
  return {
    type: "chunk",
    chunk_id: "c1",
    content: "Objection 1. It seems that...",
    reranker_score: 0.8,
    source: {
      document_id: "d1",
      document_title: "Summa Theologica",
      collection: "summa",
      author: "Thomas Aquinas",
      reference: "ST I q1 a1",
    },
    context,
  };
}

describe("bookmark cache", () => {
  it("does not let an older token request replace the active token cache", async () => {
    let resolveOld!: (response: Response) => void;
    let resolveCurrent!: (response: Response) => void;
    const oldRequest = new Promise<Response>((resolve) => { resolveOld = resolve; });
    const currentRequest = new Promise<Response>((resolve) => { resolveCurrent = resolve; });
    const fetchMock = vi.fn()
      .mockReturnValueOnce(oldRequest)
      .mockReturnValueOnce(currentRequest);
    vi.stubGlobal("fetch", fetchMock);

    const oldResult = getBookmarks("old-token");
    const currentResult = getBookmarks("current-token");
    resolveCurrent(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("current")] }), { status: 200 }));
    await expect(currentResult).resolves.toEqual([bookmarkFixture("current")]);
    resolveOld(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("old")] }), { status: 200 }));
    await expect(oldResult).resolves.toEqual([bookmarkFixture("old")]);

    await expect(getBookmarks("current-token")).resolves.toEqual([bookmarkFixture("current")]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("can force a fresh read without waiting for the cache TTL", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("old")] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("fresh")] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getBookmarks("token")).resolves.toEqual([bookmarkFixture("old")]);
    await expect(getBookmarks("token", true)).resolves.toEqual([bookmarkFixture("fresh")]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("makes a forced page read supersede an older warm-cache request", async () => {
    let resolveWarm!: (response: Response) => void;
    let resolveFresh!: (response: Response) => void;
    const fetchMock = vi.fn()
      .mockReturnValueOnce(new Promise<Response>((resolve) => { resolveWarm = resolve; }))
      .mockReturnValueOnce(new Promise<Response>((resolve) => { resolveFresh = resolve; }));
    vi.stubGlobal("fetch", fetchMock);

    const warmRead = getBookmarks("token");
    const forcedRead = getBookmarks("token", true);
    resolveFresh(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("fresh")] }), { status: 200 }));
    await expect(forcedRead).resolves.toEqual([bookmarkFixture("fresh")]);
    resolveWarm(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("old")] }), { status: 200 }));
    await expect(warmRead).resolves.toEqual([bookmarkFixture("fresh")]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gives every coalesced caller fresh data when a mutation overlaps a list read", async () => {
    let resolveList!: (response: Response) => void;
    let resolveDelete!: (response: Response) => void;
    let resolveFreshList!: (response: Response) => void;
    const fetchMock = vi.fn()
      .mockReturnValueOnce(new Promise<Response>((resolve) => { resolveList = resolve; }))
      .mockReturnValueOnce(new Promise<Response>((resolve) => { resolveDelete = resolve; }))
      .mockReturnValueOnce(new Promise<Response>((resolve) => { resolveFreshList = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const firstCaller = getBookmarks("token");
    const coalescedCaller = getBookmarks("token");
    const deletion = removeBookmark("token", "removed");

    resolveList(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("removed")] }), { status: 200 }));
    resolveDelete(new Response(null, { status: 204 }));
    await deletion;
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    resolveFreshList(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("kept")] }), { status: 200 }));
    await expect(firstCaller).resolves.toEqual([bookmarkFixture("kept")]);
    await expect(coalescedCaller).resolves.toEqual([bookmarkFixture("kept")]);

    await expect(getBookmarks("token")).resolves.toEqual([bookmarkFixture("kept")]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("coordinates a mutation across access-token rotation for the same user", async () => {
    const oldToken = jwtForSubject("user-1", "old");
    const newToken = jwtForSubject("user-1", "new");
    let resolveDelete!: (response: Response) => void;
    const fetchMock = vi.fn()
      .mockReturnValueOnce(new Promise<Response>((resolve) => { resolveDelete = resolve; }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("kept")] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const deletion = removeBookmark(oldToken, "removed");
    const rotatedRead = getBookmarks(newToken);
    expect(fetchMock).toHaveBeenCalledOnce();
    resolveDelete(new Response(null, { status: 204 }));

    await deletion;
    await expect(rotatedRead).resolves.toEqual([bookmarkFixture("kept")]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("times out a hung mutation and allows later reads to recover", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockImplementationOnce((_url: string, options?: RequestInit) => new Promise<Response>((_resolve, reject) => {
        options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ bookmarks: [bookmarkFixture("kept")] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const removalResult = expect(removeBookmark("token", "removed")).rejects.toThrow("timed out");
    const recoveredRead = getBookmarks("token");
    await vi.advanceTimersByTimeAsync(10_000);

    await removalResult;
    await expect(recoveredRead).resolves.toEqual([bookmarkFixture("kept")]);
    vi.useRealTimers();
  });
});

describe("streamSearch", () => {
  it("uses the authenticated proxy endpoint and preserves the request contract", async () => {
    const cb = callbacks();
    const fetchMock = vi.fn().mockResolvedValue(response({
      type: "done", search_id: "search-1", result_count: 0,
    }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await streamSearch(
      "jwt-token",
      "grace",
      { collections: ["bible"], translation: "CPDV" },
      3,
      cb,
      controller.signal,
    );

    expect(fetchMock).toHaveBeenCalledWith("/v1/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer jwt-token",
      },
      body: JSON.stringify({
        query: "grace",
        filters: { collections: ["bible"], translation: "CPDV" },
        quota: 3,
      }),
      signal: controller.signal,
    });
  });

  it("rejects a successful response with no body", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 200 })));

    await expect(streamSearch("token", "grace", { collections: ["bible"] }, 3, cb))
      .rejects.toThrow();
  });

  it("reports backend details for non-success responses", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Search service unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    )));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onError).toHaveBeenCalledWith("Search service unavailable");
  });

  it("falls back to the HTTP status when a non-success body is unreadable", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not-json", { status: 502 })));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onError).toHaveBeenCalledWith("API error 502");
  });

  it("classifies a daily rate limit and preserves Retry-After", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Daily search quota exhausted" }),
      {
        status: 429,
        headers: { "Content-Type": "application/json", "Retry-After": "7200" },
      },
    )));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onRateLimit).toHaveBeenCalledWith(7200, "daily");
  });

  it("classifies other rate limits as per-minute", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Too many searches" }),
      { status: 429, headers: { "Content-Type": "application/json" } },
    )));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onRateLimit).toHaveBeenCalledWith(null, "per_minute");
  });

  it("silently returns when the authenticated request is cancelled", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")));

    await expect(streamSearch("token", "grace", { collections: ["bible"] }, 3, cb))
      .resolves.toBeUndefined();

    expect(cb.onError).not.toHaveBeenCalled();
  });
});

describe("streamGuestSearch", () => {
  it("uses the same terminal parsing contract as authenticated search", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      type: "done",
      search_id: null,
      persisted: false,
      result_count: 0,
      outcome: "no_candidates",
      collection_outcomes: { bible: "no_candidates" },
    })));

    await streamGuestSearch("guest-session-token-with-at-least-32-chars", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onDone).toHaveBeenCalledWith(
      null, 0, "no_candidates", { bible: "no_candidates" }, false,
    );
    expect(cb.onError).not.toHaveBeenCalled();
  });

  it("rejects malformed guest SSE", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response("data: nope\n", { status: 200 }),
    ));

    await expect(
      streamGuestSearch("guest-session-token-with-at-least-32-chars", "grace", { collections: ["bible"] }, 3, cb),
    ).rejects.toThrow("invalid stream event");
  });

  it("releases ranked guest results before terminal transfer completion", async () => {
    const cb = callbacks();
    const encoder = new TextEncoder();
    const read = vi.fn()
      .mockResolvedValueOnce({ done: false, value: encoder.encode('data: {"type":"results_ready","result_count":4}\n\n') })
      .mockResolvedValueOnce({ done: false, value: encoder.encode('data: {"type":"done","search_id":null,"result_count":4}\n\n') })
      .mockResolvedValueOnce({ done: true, value: undefined });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read }) },
    }));

    await streamGuestSearch("guest-session-token-with-at-least-32-chars", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onResultsReady).toHaveBeenCalledWith(4);
    expect(cb.onDone).toHaveBeenCalledOnce();
    expect(cb.onResultsReady.mock.invocationCallOrder[0]).toBeLessThan(cb.onDone.mock.invocationCallOrder[0]);
  });

  it("forwards the attached passage like the authenticated path", async () => {
    const cb = callbacks();
    const context = {
      relation: "answers",
      parts: [{ content: "Objection 2. Further...", reference: "ST I q1 a1", unit_label: "Objection 2", anchor: "a/0" }],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(
      chunkEvent(context), { type: "done", search_id: "s1", result_count: 1 },
    )));

    await streamGuestSearch("guest-session-token-with-at-least-32-chars", "grace", { collections: ["summa"] }, 3, cb);

    expect(cb.onChunk.mock.calls[0][0].context).toEqual(context);
  });
});

describe("claimGuestSession", () => {
  it("preserves the response status and detail for retry decisions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Guest search is still completing" }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    )));

    await expect(claimGuestSession("jwt", "guest-session-token-with-at-least-32-chars", []))
      .rejects.toEqual(expect.objectContaining<Partial<GuestClaimHttpError>>({
        name: "GuestClaimHttpError",
        status: 409,
        message: "Guest search is still completing",
      }));
  });
});

describe("getSearchHistoryPage", () => {
  it("uses the relative proxy path and carries cursor and query parameters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ searches: [], next_cursor: null }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await getSearchHistoryPage("token", { cursor: "opaque", limit: 20, query: "grace" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/v1/searches?cursor=opaque&limit=20&q=grace",
      expect.objectContaining({ headers: { Authorization: "Bearer token" } }),
    );
  });
});

describe("deleteSearch", () => {
  it("treats an already-deleted search as an idempotent success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));

    await expect(deleteSearch("token", "search-1")).resolves.toBeUndefined();
  });

  it("still reports service failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 503 })));

    await expect(deleteSearch("token", "search-1")).rejects.toThrow("API error 503");
  });
});

describe("getSearchResults", () => {
  it("preserves HTTP status and backend detail for restore failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Search not found" }),
      { status: 404, headers: { "Content-Type": "application/json" } },
    )));

    await expect(getSearchResults("token", "search-1")).rejects.toEqual(
      expect.objectContaining<SearchRestoreHttpError>({
        name: "SearchRestoreHttpError",
        status: 404,
        message: "Search not found",
      }),
    );
  });

  it("bounds a restore request that never settles", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_url: string, options?: RequestInit) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    })));

    const result = expect(getSearchResults("token", "search-1", undefined, 25))
      .rejects.toThrow("took too long");
    await vi.advanceTimersByTimeAsync(25);
    await result;
    vi.useRealTimers();
  });

  it("preserves caller cancellation as AbortError", async () => {
    const caller = new AbortController();
    vi.stubGlobal("fetch", vi.fn((_url: string, options?: RequestInit) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    })));

    const result = expect(getSearchResults("token", "search-1", caller.signal, 1_000))
      .rejects.toMatchObject({ name: "AbortError" });
    caller.abort();
    await result;
  });
});

describe("reading progress", () => {
  it("uses relative authenticated routes for reads and writes", async () => {
    const item = {
      document_id: "doc-1", chapter_key: "chapter-1", chapter_label: "Chapter 1",
      anchor: null, updated_at: "2026-08-04T00:00:00Z", collection: "summa",
      document_title: "Summa", author: null,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(item), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(item), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await getReadingProgress("token", "doc-1");
    await putReadingProgress("token", "doc-1", "chapter-1");

    expect(fetchMock.mock.calls[0][0]).toBe("/v1/reading-progress/doc-1");
    expect(fetchMock.mock.calls[1][0]).toBe("/v1/reading-progress/doc-1");
    expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ chapter_key: "chapter-1", anchor: null }),
    }));
  });

  it("treats missing progress as an empty optional state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })));
    await expect(getReadingProgress("token", "doc-1")).resolves.toBeNull();
  });
});

describe("product feedback", () => {
  it("uses the relative authenticated proxy and preserves only the supplied bounded context", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ feedback_id: "feedback-1" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await submitProductFeedback("token", {
      category: "bug",
      message: "The reader did not advance.",
      contact_allowed: false,
      route: "/reader",
      error_code: "unknown",
    });

    expect(fetchMock).toHaveBeenCalledWith("/v1/product-feedback", expect.objectContaining({
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer token" },
    }));
    const payload = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(payload).not.toHaveProperty("query");
    expect(payload).not.toHaveProperty("content");
  });
});
