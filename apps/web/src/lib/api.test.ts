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
    source: { document_id: "d1", title: "Summa Theologica", collection: "summa" },
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
  it("accepts the old done contract and derives a successful outcome", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      type: "done", search_id: "search-1", result_count: 2,
    })));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onDone).toHaveBeenCalledWith("search-1", 2, "success", {}, true);
    expect(cb.onError).not.toHaveBeenCalled();
  });

  it("preserves new degraded and unpersisted terminal metadata", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      type: "done",
      search_id: null,
      persisted: false,
      result_count: 1,
      outcome: "degraded_success",
      collection_outcomes: { bible: "results_degraded" },
    })));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onDone).toHaveBeenCalledWith(
      null, 1, "degraded_success", { bible: "results_degraded" },
      false,
    );
  });

  it("rejects malformed SSE instead of converting it to no results", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response("data: {not-json}\n", { status: 200 }),
    ));

    await expect(
      streamSearch("token", "grace", { collections: ["bible"] }, 3, cb),
    ).rejects.toThrow("invalid stream event");
    expect(cb.onDone).not.toHaveBeenCalled();
  });

  it("reports a stream that closes before a terminal event", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      type: "status", phase: "ranking",
    })));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onError).toHaveBeenCalledWith(
      "The connection closed before the search finished.",
      "stream_interrupted",
      "connection",
    );
  });

  it("does not invalidate done when a later stream read fails", async () => {
    const cb = callbacks();
    const encoder = new TextEncoder();
    const read = vi.fn()
      .mockResolvedValueOnce({
        done: false,
        value: encoder.encode(
          'data: {"type":"done","search_id":"search-1","result_count":1}\n',
        ),
      })
      .mockRejectedValueOnce(new Error("connection reset"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => ({ read }) },
    }));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onDone).toHaveBeenCalledOnce();
    expect(cb.onError).not.toHaveBeenCalled();
  });

  it("forwards the attached passage to the caller", async () => {
    // This handler rebuilds the chunk event field by field, so a dropped field is a
    // silent runtime omission rather than a type error.
    const cb = callbacks();
    const context = {
      relation: "answered_by",
      parts: [{ content: "I answer that...", reference: "ST I q1 a1", unit_label: "I answer that", anchor: "a/1" }],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(
      chunkEvent(context), { type: "done", search_id: "s1", result_count: 1 },
    )));

    await streamSearch("token", "grace", { collections: ["summa"] }, 3, cb);

    expect(cb.onChunk.mock.calls[0][0].context).toEqual(context);
  });

  it("forwards a reply's attached objection, which renders above the match", async () => {
    // Both relations travel the same field; a handler that special-cased one would
    // leave the other, which is ~95% of live Summa results, without its context.
    const cb = callbacks();
    const context = {
      relation: "answers",
      parts: [{ content: "Objection 2. Further...", reference: "ST I q1 a1", unit_label: "Objection 2", anchor: "a/0" }],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(
      chunkEvent(context), { type: "done", search_id: "s1", result_count: 1 },
    )));

    await streamSearch("token", "grace", { collections: ["summa"] }, 3, cb);

    expect(cb.onChunk.mock.calls[0][0].context).toEqual(context);
  });

  it("gives an unattached result a null context rather than undefined", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(
      chunkEvent(undefined), { type: "done", search_id: "s1", result_count: 1 },
    )));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onChunk.mock.calls[0][0].context).toBeNull();
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
