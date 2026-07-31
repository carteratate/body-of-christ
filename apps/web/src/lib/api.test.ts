import { afterEach, describe, expect, it, vi } from "vitest";

import { streamGuestSearch, streamSearch, type SearchStreamCallbacks } from "./api";

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
