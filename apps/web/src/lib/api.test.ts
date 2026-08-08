import { afterEach, describe, expect, it, vi } from "vitest";

import { deleteSearch, getReadingProgress, getSearchHistoryPage, putReadingProgress, streamGuestSearch, streamSearch, submitProductFeedback, type SearchStreamCallbacks } from "./api";

function callbacks() {
  return {
    onChunk: vi.fn(),
    onExplanationDelta: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
    onRateLimit: vi.fn(),
    onStatus: vi.fn(),
  } satisfies SearchStreamCallbacks;
}

function response(...events: unknown[]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n`).join("");
  return new Response(body, { status: 200 });
}

afterEach(() => {
  vi.unstubAllGlobals();
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

    await streamGuestSearch("grace", { collections: ["bible"] }, 3, cb);

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
      streamGuestSearch("grace", { collections: ["bible"] }, 3, cb),
    ).rejects.toThrow("invalid stream event");
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
