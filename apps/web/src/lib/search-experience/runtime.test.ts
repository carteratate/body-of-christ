import { describe, expect, it, vi } from "vitest";

import type { ChunkResult } from "@/lib/search-stream";
import { createSearchExperience } from "./runtime";
import type {
  AudienceAdapter,
  SearchExperiencePorts,
  SearchRequest,
  SearchTransportCallbacks,
} from "./types";

const REQUEST: SearchRequest = {
  query: "What is grace?",
  collections: ["bible", "catechism"],
  translation: "CPDV",
  quota: 4,
  origin: "fresh",
};

function passage(id: string): ChunkResult {
  return {
    chunk_id: id,
    content: `Passage ${id}`,
    source: {
      collection: "bible",
      document_title: "Romans",
      author: "Paul",
      reference: "Romans 5:1",
      document_id: "romans",
      position: 1,
    },
    reranker_score: 0.9,
    explanation: null,
  };
}

interface ScriptedRun {
  readonly request: SearchRequest;
  readonly callbacks: SearchTransportCallbacks;
  readonly signal: AbortSignal;
  readonly credential?: string;
}

function authenticatedFixture(overrides: Partial<SearchExperiencePorts> = {}) {
  const runs: ScriptedRun[] = [];
  const audience: AudienceAdapter = {
    kind: "authenticated",
    async search(credential, request, callbacks, signal) {
      runs.push({ credential, request, callbacks, signal });
    },
  };
  const runtime = createSearchExperience({
    audience,
    credentials: { current: () => "current-token" },
    ...overrides,
  });
  return { runtime, runs };
}

function guestFixture(overrides: Partial<SearchExperiencePorts> = {}) {
  const runs: ScriptedRun[] = [];
  const audience: AudienceAdapter = {
    kind: "guest",
    async search(request, callbacks, signal) {
      runs.push({ request, callbacks, signal });
    },
  };
  const runtime = createSearchExperience({ audience, ...overrides });
  return { runtime, runs };
}

describe("search-experience runtime", () => {
  it("publishes immutable snapshots through read and subscribe", () => {
    const { runtime, runs } = authenticatedFixture();
    const listener = vi.fn();
    const unsubscribe = runtime.subscribe(listener);
    const mutableCollections = ["bible", "catechism"];

    runtime.send({ type: "submit", request: { ...REQUEST, collections: mutableCollections } });
    mutableCollections.splice(0);

    const current = runtime.read();
    expect(current).toMatchObject({ status: "active-search", runId: 1 });
    if (current.status !== "active-search") throw new Error("Expected active search");
    expect(current.request.collections).toEqual(["bible", "catechism"]);
    expect(Object.isFrozen(current)).toBe(true);
    expect(Object.isFrozen(current.request)).toBe(true);
    expect(Object.isFrozen(current.request.collections)).toBe(true);
    expect(Object.isFrozen(current.presentation)).toBe(true);
    expect(() => {
      (current.presentation as { resultsReady: boolean }).resultsReady = true;
    }).toThrow();
    expect(runs[0].credential).toBe("current-token");
    expect(listener).toHaveBeenCalledOnce();

    unsubscribe();
    runs[0].callbacks.onStatus("searching");
    expect(listener).toHaveBeenCalledOnce();
  });

  it("buffers Passages and explanations until authenticated completion and animation reveal", () => {
    const { runtime, runs } = authenticatedFixture();
    runtime.send({ type: "submit", request: REQUEST });
    const runId = runtime.read().runId;

    runs[0].callbacks.onPassage(passage("p1"));
    runs[0].callbacks.onExplanationDelta("p1", "First ");
    expect(runtime.read()).toMatchObject({ status: "active-search", passages: [] });

    runs[0].callbacks.onDone("search-1", 1, "success", { bible: "results" }, true);
    let current = runtime.read();
    expect(current).toMatchObject({
      status: "active-search",
      transport: { status: "complete", searchId: "search-1" },
      presentation: { status: "animating", resultsReady: true },
      passages: [],
    });

    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });
    current = runtime.read();
    expect(current).toMatchObject({
      presentation: { status: "fading" },
      passages: [{ chunk_id: "p1", explanation: "First " }],
    });

    runs[0].callbacks.onExplanationDelta("p1", "second");
    expect(runtime.read()).toMatchObject({
      passages: [{ chunk_id: "p1", explanation: "First second" }],
    });
    runtime.send({ type: "animation", runId, milestone: "fade-complete" });
    expect(runtime.read()).toMatchObject({ presentation: { status: "revealed" } });
  });

  it("keeps guest ranked readiness separate from final completion", () => {
    const completed = vi.fn();
    const { runtime, runs } = guestFixture({
      guestAccess: {
        canSearch: () => true,
        requestSignup: vi.fn(),
        recordCompletedSearch: completed,
      },
    });
    runtime.send({ type: "submit", request: REQUEST });
    const runId = runtime.read().runId;
    runs[0].callbacks.onPassage(passage("p1"));
    runs[0].callbacks.onResultsReady(1);

    expect(runtime.read()).toMatchObject({
      transport: { status: "ranked-ready", resultCount: 1 },
      presentation: { status: "animating", resultsReady: true },
    });
    expect(completed).not.toHaveBeenCalled();
    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });
    runs[0].callbacks.onDone(null, 1, "success", { bible: "results" }, true);
    expect(runtime.read()).toMatchObject({
      transport: { status: "complete" },
      presentation: { status: "fading" },
    });
    expect(completed).toHaveBeenCalledOnce();
  });

  it("rejects guest completion before ranked results are ready", () => {
    const { runtime, runs } = guestFixture();
    runtime.send({ type: "submit", request: REQUEST });
    expect(() => runs[0].callbacks.onDone(null, 0, "no_candidates", {}, true))
      .toThrow(/before ranked results are ready/);
    expect(runtime.read()).toMatchObject({
      status: "active-search",
      transport: { status: "preparing" },
      presentation: { status: "animating", resultsReady: false },
    });
  });

  it("copies and freezes nested Passage metadata before exposing it", () => {
    const { runtime, runs } = authenticatedFixture();
    const transportPassage = passage("p1");
    transportPassage.source.metadata = { citation: { page: 12 } };
    runtime.send({ type: "submit", request: REQUEST });
    const runId = runtime.read().runId;
    runs[0].callbacks.onPassage(transportPassage);
    runs[0].callbacks.onDone("search-1", 1, "success", {}, true);
    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });
    transportPassage.source.metadata.citation = { page: 99 };

    const current = runtime.read();
    if (current.status !== "active-search") throw new Error("Expected active search");
    expect(current.passages[0].source.metadata).toEqual({ citation: { page: 12 } });
    expect(Object.isFrozen((current.passages[0].source.metadata as { citation: object }).citation)).toBe(true);
  });

  it("aborts the previous run and rejects its transport and animation events", () => {
    const { runtime, runs } = authenticatedFixture();
    runtime.send({ type: "submit", request: REQUEST });
    const firstRunId = runtime.read().runId;
    runtime.send({ type: "submit", request: { ...REQUEST, query: "What is hope?" } });

    expect(runs[0].signal.aborted).toBe(true);
    expect(runtime.read()).toMatchObject({ runId: firstRunId + 1, request: { query: "What is hope?" } });
    runs[0].callbacks.onPassage(passage("stale"));
    runs[0].callbacks.onDone("stale-search", 1, "success", {}, true);
    runtime.send({ type: "animation", runId: firstRunId, milestone: "fade-complete" });
    expect(runtime.read()).toMatchObject({
      request: { query: "What is hope?" },
      transport: { status: "preparing" },
      presentation: { status: "animating" },
      passages: [],
    });
  });

  it("treats invalid user commands as no-ops", () => {
    const { runtime, runs } = authenticatedFixture();
    const initial = runtime.read();
    runtime.send({ type: "retry" });
    runtime.send({ type: "restore", searchId: "" });
    runtime.send({ type: "submit", request: { ...REQUEST, query: "" } });
    runtime.send({ type: "animation", runId: 42, milestone: "ready-to-reveal" });
    runtime.send({ type: "dismiss-rate-limit" });
    expect(runtime.read()).toBe(initial);
    expect(runs).toHaveLength(0);
  });

  it("fails loudly for impossible current-run transport transitions", () => {
    const { runtime, runs } = authenticatedFixture();
    runtime.send({ type: "submit", request: REQUEST });
    expect(() => runs[0].callbacks.onResultsReady(1)).toThrow(/guest adapter/);
    runs[0].callbacks.onDone("search-1", 0, "no_candidates", {}, true);
    expect(() => runs[0].callbacks.onPassage(passage("late"))).toThrow(/terminal/);
  });

  it("keeps no-candidate, service failure, and rate limits as distinct outcomes", () => {
    const { runtime, runs } = authenticatedFixture();
    runtime.send({ type: "submit", request: REQUEST });
    const firstRun = runtime.read().runId;
    runs[0].callbacks.onDone("search-1", 0, "no_candidates", { bible: "no_candidates" }, true);
    runtime.send({ type: "animation", runId: firstRun, milestone: "ready-to-reveal" });
    expect(runtime.read()).toMatchObject({
      status: "active-search",
      transport: { status: "complete", outcome: "no_candidates" },
      passages: [],
    });

    runtime.send({ type: "submit", request: REQUEST });
    runs[1].callbacks.onError("Retrieval failed", "retrieval_failed", "retrieve", { bible: "retrieval_failed" });
    expect(runtime.read()).toMatchObject({
      status: "failure",
      failure: { code: "retrieval_failed", rateLimit: null },
    });

    runtime.send({ type: "retry" });
    runs[2].callbacks.onRateLimit(null, "per_minute");
    expect(runtime.read()).toMatchObject({
      status: "failure",
      failure: { rateLimit: { type: "per_minute", retryAfter: 60, open: true } },
    });
    runtime.send({ type: "dismiss-rate-limit" });
    expect(runtime.read()).toMatchObject({ failure: { rateLimit: { open: false } } });
  });

  it("retries the frozen submitted criteria rather than later caller mutations", () => {
    const { runtime, runs } = authenticatedFixture();
    const request = { ...REQUEST, collections: ["bible"] };
    runtime.send({ type: "submit", request });
    request.query = "Changed draft";
    request.collections.push("summa");
    runs[0].callbacks.onError("Network unavailable");
    runtime.send({ type: "retry" });

    expect(runs[1].request).toEqual({ ...REQUEST, collections: ["bible"] });
    expect(runs[0].signal.aborted).toBe(true);
  });

  it("clears only the pending entry owned by each cancelled or terminal run", () => {
    const begin = vi.fn();
    const clear = vi.fn();
    const refresh = vi.fn();
    let id = 0;
    const { runtime, runs } = authenticatedFixture({
      pendingHistory: { begin, clear, refresh },
      ids: { pendingEntry: () => `pending-${++id}` },
    });

    runtime.send({ type: "submit", request: REQUEST });
    runtime.send({ type: "submit", request: { ...REQUEST, query: "Second" } });
    expect(clear).toHaveBeenCalledWith("pending-1");
    expect(clear).not.toHaveBeenCalledWith("pending-2");
    runs[0].callbacks.onError("stale");
    expect(clear).not.toHaveBeenCalledWith("pending-2");
    runs[1].callbacks.onDone("search-2", 0, "no_candidates", {}, true);
    expect(clear).toHaveBeenLastCalledWith("pending-2");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("does not let secondary adapter failures discard available Passages", async () => {
    const rejects = () => Promise.reject(new Error("secondary failed"));
    const { runtime, runs } = authenticatedFixture({
      pendingHistory: { begin: rejects, clear: rejects, refresh: rejects },
      analytics: { searchCompleted: rejects, searchFailed: rejects },
      ids: { pendingEntry: () => "pending" },
    });
    runtime.send({ type: "submit", request: REQUEST });
    const runId = runtime.read().runId;
    runs[0].callbacks.onPassage(passage("p1"));
    runs[0].callbacks.onDone("search-1", 1, "success", {}, true);
    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });
    await Promise.resolve();
    expect(runtime.read()).toMatchObject({ status: "active-search", passages: [{ chunk_id: "p1" }] });
  });

  it("stores guest continuity only after reveal and refreshes it later", () => {
    const save = vi.fn();
    const { runtime, runs } = guestFixture({
      guestContinuity: { save, clear: vi.fn() },
      time: { now: () => 1234 },
    });
    runtime.send({ type: "submit", request: REQUEST });
    const runId = runtime.read().runId;
    runs[0].callbacks.onPassage(passage("p1"));
    runs[0].callbacks.onResultsReady(1);
    runs[0].callbacks.onExplanationDelta("p1", "before");
    expect(save).not.toHaveBeenCalled();

    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });
    expect(save).toHaveBeenLastCalledWith(expect.objectContaining({
      savedAt: 1234,
      searchId: null,
      passages: [expect.objectContaining({ explanation: "before" })],
    }));
    runs[0].callbacks.onExplanationDelta("p1", " after");
    runs[0].callbacks.onDone(null, 1, "success", {}, true);
    expect(save).toHaveBeenCalledTimes(3);
    expect(save).toHaveBeenLastCalledWith(expect.objectContaining({ outcome: "success" }));
  });

  it("aborts stale restoration and exposes only the replacement result", async () => {
    const restores: Array<{
      searchId: string;
      signal: AbortSignal;
      resolve: (value: never) => void;
    }> = [];
    const savedSearch = {
      restore: vi.fn((_credential: string, searchId: string, signal: AbortSignal) =>
        new Promise<never>((resolve) => restores.push({ searchId, signal, resolve }))
      ),
    };
    const { runtime } = authenticatedFixture({ savedSearch });
    runtime.send({ type: "restore", searchId: "old" });
    runtime.send({ type: "restore", searchId: "new" });
    expect(restores[0].signal.aborted).toBe(true);

    restores[0].resolve({
      searchId: "old",
      request: REQUEST,
      passages: [passage("old")],
      warning: null,
    } as never);
    restores[1].resolve({
      searchId: "new",
      request: REQUEST,
      passages: [passage("new")],
      warning: "One Passage is unavailable.",
    } as never);
    await Promise.resolve();
    await Promise.resolve();
    expect(runtime.read()).toMatchObject({
      status: "restored-results",
      searchId: "new",
      passages: [{ chunk_id: "new" }],
      warning: "One Passage is unavailable.",
    });
  });

  it("cancels work on identity changes and disposal", () => {
    const { runtime, runs } = authenticatedFixture();
    runtime.send({ type: "identity-changed", identity: "user-1" });
    runtime.send({ type: "submit", request: REQUEST });
    runtime.send({ type: "identity-changed", identity: "user-2" });
    expect(runs[0].signal.aborted).toBe(true);
    expect(runtime.read()).toMatchObject({ status: "idle" });

    runtime.send({ type: "submit", request: REQUEST });
    runtime.send({ type: "dispose" });
    expect(runs[1].signal.aborted).toBe(true);
    const disposedSnapshot = runtime.read();
    runtime.send({ type: "submit", request: REQUEST });
    expect(runtime.read()).toBe(disposedSnapshot);
    expect(runs).toHaveLength(2);
  });
});
