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

  it("does not expose backend details for non-success responses", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Search service unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    )));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onError).toHaveBeenCalledWith(
      "We couldn't complete this search. Try again.",
      "server_error",
      "server",
    );
  });

  it("does not expose an HTTP status when a non-success body is unreadable", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not-json", { status: 502 })));

    await streamSearch("token", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onError).toHaveBeenCalledWith(
      "We couldn't complete this search. Try again.",
      "server_error",
      "server",
    );
  });

  it("turns FastAPI validation arrays into a safe request error", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        detail: [{
          type: "string_too_long",
          loc: ["body", "query"],
          msg: "String should have at most 1000 characters",
          input: "x".repeat(2990),
        }],
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    )));

    await expect(streamSearch(
      "token",
      "x".repeat(2990),
      { collections: ["medieval"] },
      3,
      cb,
    )).resolves.toBeUndefined();

    expect(cb.onError).toHaveBeenCalledWith(
      "This search couldn't be submitted. Check the question and selected sources.",
      "invalid_request",
      "validation",
    );
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
  it("uses the guest proxy endpoint and preserves the request contract", async () => {
    const cb = callbacks();
    const fetchMock = vi.fn().mockResolvedValue(response({
      type: "done",
      search_id: null,
      persisted: false,
      result_count: 0,
    }));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await streamGuestSearch(
      "guest-session-token-with-at-least-32-chars",
      "grace",
      { collections: ["bible"], translation: "CPDV" },
      3,
      cb,
      controller.signal,
    );

    expect(fetchMock).toHaveBeenCalledWith("/v1/search/guest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: "grace",
        filters: { collections: ["bible"], translation: "CPDV" },
        quota: 3,
        session_token: "guest-session-token-with-at-least-32-chars",
      }),
      signal: controller.signal,
    });
  });

  it("rejects a successful guest response with no body", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 200 })));

    await expect(
      streamGuestSearch("guest-session-token-with-at-least-32-chars", "grace", { collections: ["bible"] }, 3, cb),
    ).rejects.toThrow();
  });

  it("does not expose backend details for guest non-success responses", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Guest search unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    )));

    await streamGuestSearch("guest-session-token-with-at-least-32-chars", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onError).toHaveBeenCalledWith(
      "We couldn't complete this search. Try again.",
      "server_error",
      "server",
    );
  });

  it("opens the guest signup path when the trial is exhausted", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "trial_exhausted" }),
      { status: 429, headers: { "Content-Type": "application/json" } },
    )));

    await streamGuestSearch("guest-session-token-with-at-least-32-chars", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onError).toHaveBeenCalledWith("trial_exhausted");
    expect(cb.onRateLimit).not.toHaveBeenCalled();
  });

  it("classifies other guest limits as per-minute without Retry-After", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Too many searches" }),
      { status: 429, headers: { "Content-Type": "application/json", "Retry-After": "120" } },
    )));

    await streamGuestSearch("guest-session-token-with-at-least-32-chars", "grace", { collections: ["bible"] }, 3, cb);

    expect(cb.onRateLimit).toHaveBeenCalledWith(null, "per_minute");
  });

  it("silently returns when the guest request is cancelled", async () => {
    const cb = callbacks();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")));

    await expect(streamGuestSearch(
      "guest-session-token-with-at-least-32-chars",
      "grace",
      { collections: ["bible"] },
      3,
      cb,
    )).resolves.toBeUndefined();

    expect(cb.onError).not.toHaveBeenCalled();
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

  it("sends the complete guest preference draft and returns its confirmation", async () => {
    const draft = {
      preferred_translation: "CPDV",
      default_collections: ["bible"],
      default_quota: 10,
      last_standard_quota: 5 as const,
    };
    const confirmed = {
      ...draft,
      theme: "dark" as const,
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      searches_imported: 2,
      passages_saved: 1,
      preferences: confirmed,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(claimGuestSession(
      "jwt",
      "guest-session-token-with-at-least-32-chars",
      [],
      draft,
    )).resolves.toEqual(expect.objectContaining({ preferences: confirmed }));

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      session_token: "guest-session-token-with-at-least-32-chars",
      saved_chunk_ids: [],
      preferences: draft,
    });
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

describe("reader refusal for excerpt-only documents (issue #265)", () => {
  it("turns a 403 reader_restricted into a ReaderRestrictedError with the source", async () => {
    const { getToc, getReaderChapter, ReaderRestrictedError } = await import("./api");
    const body = { detail: { code: "reader_restricted", message: "x", source_url: "https://example.org/a" } };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    try {
      await expect(getToc("t", "doc")).rejects.toBeInstanceOf(ReaderRestrictedError);
      const caught = await getReaderChapter("t", "doc", {}).catch((e) => e);
      expect(caught).toBeInstanceOf(ReaderRestrictedError);
      expect(caught.sourceUrl).toBe("https://example.org/a");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("drops a source link that is not http(s)", async () => {
    const { getToc } = await import("./api");
    const body = { detail: { code: "reader_restricted", source_url: "javascript:alert(1)" } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 403 })));
    try {
      expect((await getToc("t", "doc").catch((e) => e)).sourceUrl).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("keeps any other 403 an ordinary API error", async () => {
    const { getToc, ReaderRestrictedError } = await import("./api");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "Document is not part of this guest session" }), { status: 403 })));
    try {
      const caught = await getToc("t", "doc").catch((e) => e);
      expect(caught).not.toBeInstanceOf(ReaderRestrictedError);
      expect(caught.message).toBe("API error 403");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("retired anchors (corpus cleanup 2.4a)", () => {
  it("sends a #retired-<release> anchor to the API unchanged, encoded as %23", async () => {
    const { getReaderChapter } = await import("./api");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    try {
      await getReaderChapter("t", "doc", { anchor: "c1/p2#retired-rel-1" });
      const requested = String((fetchMock.mock.calls[0] as unknown[])[0]);
      expect(requested).toBe("/v1/documents/doc/reader?anchor=c1%2Fp2%23retired-rel-1");
      expect(new URL(requested, "https://theo-corpus.com").searchParams.get("anchor"))
        .toBe("c1/p2#retired-rel-1");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("reader answers for removed and moved documents (corpus cleanup 2.4b)", () => {
  async function failWith(status: number, body: unknown) {
    const { getReaderChapter } = await import("./api");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
    try {
      return await getReaderChapter("t", "doc", { anchor: "a" }).then(() => null, (error: unknown) => error);
    } finally {
      vi.unstubAllGlobals();
    }
  }

  it("turns a 410 into a ReaderRemovedError carrying the tombstone", async () => {
    const { ReaderRemovedError } = await import("./api");
    const error = await failWith(410, {
      detail: "removed",
      tombstone: { entity: "passage", rule: "G", reason_code: "debris", public_reason: "A heading.", retired_at: "2026-12-01T00:00:00Z" },
    });
    expect(error).toBeInstanceOf(ReaderRemovedError);
    expect((error as InstanceType<typeof ReaderRemovedError>).tombstone.public_reason).toBe("A heading.");
  });

  it("turns a 404 with a redirect into a ReaderMovedError", async () => {
    const { ReaderMovedError } = await import("./api");
    const error = await failWith(404, { detail: "moved", redirect: { kind: "moved", document_id: "doc-b", anchor: "x" } });
    expect(error).toBeInstanceOf(ReaderMovedError);
    expect((error as InstanceType<typeof ReaderMovedError>).redirect).toMatchObject({ document_id: "doc-b", anchor: "x" });
  });

  it("keeps a plain 404 as today's not-found error", async () => {
    const error = await failWith(404, { detail: "Document not found" });
    expect((error as Error).message).toBe("API error 404");
  });
});
