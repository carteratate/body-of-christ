import { describe, expect, it, vi } from "vitest";

import {
  consumeSearchStream,
  SearchStreamProtocolError,
  type SearchStreamCallbacks,
} from "./search-stream";

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

function streamFromText(text: string): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
}

function streamFromBytes(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

function data(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n`;
}

function passage(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    type: "chunk",
    chunk_id: "passage-1",
    content: "Grace perfects nature.",
    source: {
      collection: "summa",
      document_title: "Summa Theologica",
      author: "Thomas Aquinas",
      reference: "ST I q1 a1",
      document_id: "document-1",
    },
    ...overrides,
  };
}

describe("consumeSearchStream", () => {
  it("normalizes a Passage and legacy completion through the public callbacks", async () => {
    const cb = callbacks();
    const body = streamFromText([
      "data: " + JSON.stringify({
        type: "chunk",
        chunk_id: "passage-1",
        content: "I answer that...",
        source: {
          collection: "summa",
          document_title: "Summa Theologica",
          author: "Thomas Aquinas",
          reference: "ST I q1 a1",
          document_id: "document-1",
          anchor: "a/1",
        },
        context: {
          relation: "answers",
          parts: [{
            content: "Objection 1...",
            reference: "ST I q1 a1 obj 1",
            unit_label: "Objection 1",
            anchor: "a/0",
          }],
          additive_field: true,
        },
        additive_field: "ignored",
      }),
      "data: " + JSON.stringify({
        type: "done",
        search_id: "search-1",
        result_count: 1,
      }),
      "",
    ].join("\n"));

    await consumeSearchStream(body, cb);

    expect(cb.onChunk).toHaveBeenCalledWith({
      chunk_id: "passage-1",
      content: "I answer that...",
      source: {
        collection: "summa",
        document_title: "Summa Theologica",
        author: "Thomas Aquinas",
        reference: "ST I q1 a1",
        document_id: "document-1",
        position: null,
        anchor: "a/1",
        chapter_key: null,
        unit_label: null,
        metadata: null,
      },
      reranker_score: null,
      explanation: null,
      context: {
        relation: "answers",
        parts: [{
          content: "Objection 1...",
          reference: "ST I q1 a1 obj 1",
          unit_label: "Objection 1",
          anchor: "a/0",
        }],
      },
    });
    expect(cb.onDone).toHaveBeenCalledWith("search-1", 1, "success", {}, true);
  });

  it("delivers status and explanation updates after done without treating done as EOF", async () => {
    const cb = callbacks();
    const body = streamFromText(
      data({ type: "status", phase: "searching", collections: ["bible"] })
      + data({
        type: "done",
        search_id: null,
        persisted: false,
        result_count: 1,
        outcome: "degraded_success",
        collection_outcomes: { bible: "results_degraded" },
      })
      + data({ type: "explanation_delta", chunk_id: "passage-1", delta: "Directly relevant." }),
    );

    await consumeSearchStream(body, cb);

    expect(cb.onStatus).toHaveBeenCalledWith("searching", ["bible"]);
    expect(cb.onDone).toHaveBeenCalledWith(
      null,
      1,
      "degraded_success",
      { bible: "results_degraded" },
      false,
    );
    expect(cb.onExplanationDelta).toHaveBeenCalledWith("passage-1", "Directly relevant.");
  });

  it("accepts a valid status event when its optional callback is absent", async () => {
    const cb = callbacks();
    const callbacksWithoutStatus: SearchStreamCallbacks = {
      ...cb,
      onStatus: undefined,
    };

    await consumeSearchStream(
      streamFromText(
        data({ type: "status", phase: "ranking", collections: ["summa"] })
        + data({ type: "done", search_id: null, result_count: 0 }),
      ),
      callbacksWithoutStatus,
    );

    expect(cb.onDone).toHaveBeenCalledOnce();
  });

  it("decodes split multibyte text and arbitrary byte fragmentation", async () => {
    const cb = callbacks();
    const encoded = new TextEncoder().encode(
      data(passage({ content: "Charité ✨" }))
      + data({ type: "done", search_id: "search-1", result_count: 1 }),
    );
    const chunks = Array.from(encoded, (byte) => Uint8Array.of(byte));

    await consumeSearchStream(streamFromBytes(chunks), cb);

    expect(cb.onChunk.mock.calls[0][0].content).toBe("Charité ✨");
  });

  it("ignores comments, blank separators, empty data frames, and non-data lines", async () => {
    const cb = callbacks();
    const body = streamFromText([
      ": keepalive",
      "",
      "event: ignored",
      "data:",
      "data:    ",
      `data:${JSON.stringify({ type: "done", search_id: null, result_count: 0 })}`,
    ].join("\r\n"));

    await consumeSearchStream(body, cb);

    expect(cb.onDone).toHaveBeenCalledWith(null, 0, "no_candidates", {}, false);
  });

  it("reports a clean EOF before a terminal event as an interrupted stream", async () => {
    const cb = callbacks();

    await consumeSearchStream(
      streamFromText(data({ type: "status", phase: "ranking" })),
      cb,
    );

    expect(cb.onError).toHaveBeenCalledWith(
      "The connection closed before the search finished.",
      "stream_interrupted",
      "connection",
    );
  });

  it("uses the stable fallback when a protocol error event has no detail", async () => {
    const cb = callbacks();

    await consumeSearchStream(streamFromText(data({ type: "error", code: "pipeline_failed" })), cb);

    expect(cb.onError).toHaveBeenCalledWith("Search failed", "pipeline_failed", undefined, undefined);
  });

  it.each([
    ["invalid status", { type: "status", phase: "persisting" }],
    ["invalid Passage", passage({ content: 42 })],
    ["invalid attached context", passage({ context: { relation: "near", parts: [] } })],
    ["invalid explanation", { type: "explanation_delta", chunk_id: "passage-1", delta: 42 }],
    ["invalid completion", { type: "done", search_id: null, result_count: -1 }],
    ["invalid error", { type: "error", detail: 42 }],
  ])("rejects %s payloads with the dedicated protocol error", async (_name, event) => {
    await expect(consumeSearchStream(streamFromText(data(event)), callbacks()))
      .rejects.toBeInstanceOf(SearchStreamProtocolError);
  });

  it("rejects malformed JSON with the dedicated protocol error", async () => {
    await expect(consumeSearchStream(streamFromText("data: {broken}\n"), callbacks()))
      .rejects.toBeInstanceOf(SearchStreamProtocolError);
  });

  it("rejects unknown event types with the dedicated protocol error", async () => {
    await expect(consumeSearchStream(streamFromText(data({ type: "mystery" })), callbacks()))
      .rejects.toMatchObject({
        name: "SearchStreamProtocolError",
        message: "The search service sent an unknown stream event.",
      });
  });

  it.each([
    ["duplicate done", data({ type: "done", search_id: null, result_count: 0 })],
    ["conflicting error", data({ type: "error", detail: "late failure" })],
    ["late Passage", data(passage())],
  ])("rejects a %s event after done", async (_name, trailingEvent) => {
    const body = streamFromText(
      data({ type: "done", search_id: null, result_count: 0 }) + trailingEvent,
    );

    await expect(consumeSearchStream(body, callbacks()))
      .rejects.toBeInstanceOf(SearchStreamProtocolError);
  });

  it("rejects transport failures before completion", async () => {
    const failure = new Error("connection reset");
    const body = new ReadableStream<Uint8Array>({
      pull() {
        throw failure;
      },
    });

    await expect(consumeSearchStream(body, callbacks())).rejects.toBe(failure);
  });

  it("does not mistake a transport AbortError for caller cancellation", async () => {
    const failure = new DOMException("transport aborted", "AbortError");
    const body = new ReadableStream<Uint8Array>({
      pull() {
        throw failure;
      },
    });

    await expect(consumeSearchStream(body, callbacks())).rejects.toBe(failure);
  });

  it("keeps a completed result successful when the transport later fails", async () => {
    const cb = callbacks();
    const bytes = new TextEncoder().encode(data({
      type: "done", search_id: "search-1", result_count: 1,
    }));
    let reads = 0;
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (reads++ === 0) controller.enqueue(bytes);
        else throw new Error("connection reset");
      },
    });

    await expect(consumeSearchStream(body, cb)).resolves.toBeUndefined();
    expect(cb.onDone).toHaveBeenCalledOnce();
  });

  it("does not report a second failure when transport fails after an error event", async () => {
    const cb = callbacks();
    const bytes = new TextEncoder().encode(data({
      type: "error", detail: "Search failed", code: "pipeline_failed",
    }));
    let reads = 0;
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (reads++ === 0) controller.enqueue(bytes);
        else throw new Error("connection reset");
      },
    });

    await expect(consumeSearchStream(body, cb)).resolves.toBeUndefined();
    expect(cb.onError).toHaveBeenCalledOnce();
  });

  it("silently cancels the reader and releases its lock on caller abort", async () => {
    const cb = callbacks();
    const cancel = vi.fn();
    const body = new ReadableStream<Uint8Array>({
      pull() {
        return new Promise(() => undefined);
      },
      cancel,
    });
    const controller = new AbortController();
    const consuming = consumeSearchStream(body, cb, controller.signal);

    controller.abort();
    await consuming;

    expect(cancel).toHaveBeenCalledOnce();
    expect(cb.onError).not.toHaveBeenCalled();
    const nextReader = body.getReader();
    nextReader.releaseLock();
  });

  it("propagates callback exceptions unchanged and releases the reader lock", async () => {
    const failure = new Error("render failed");
    const cb = callbacks();
    cb.onChunk.mockImplementation(() => { throw failure; });
    const body = streamFromText(data(passage()));

    await expect(consumeSearchStream(body, cb)).rejects.toBe(failure);
    const nextReader = body.getReader();
    nextReader.releaseLock();
  });
});
