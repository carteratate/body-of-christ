import { describe, expect, expectTypeOf, it, vi } from "vitest";

import type { ChunkResult } from "@/lib/search-stream";
import { createSearchExperience } from "./runtime";
import type {
  AuthenticatedSearchExperiencePorts,
  AudienceAdapter,
  GuestSearchExperiencePorts,
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

function authenticatedFixture(
  overrides: Partial<Omit<AuthenticatedSearchExperiencePorts, "audience">> = {},
) {
  const runs: ScriptedRun[] = [];
  const audience: AudienceAdapter = {
    kind: "authenticated",
    async search(credential, request, callbacks, signal) {
      runs.push({ credential, request, callbacks, signal });
    },
  };
  const credentials = overrides.credentials ?? { current: () => "current-token" };
  const runtime = createSearchExperience({ ...overrides, audience, credentials });
  return { runtime, runs };
}

function guestFixture(
  overrides: Partial<Omit<GuestSearchExperiencePorts, "audience">> = {},
) {
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
    expect(completed).toHaveBeenCalledOnce();
    expect(completed).toHaveBeenCalledWith(1);
    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });
    runs[0].callbacks.onDone(null, 1, "success", { bible: "results" }, true);
    expect(runtime.read()).toMatchObject({
      transport: { status: "complete" },
      presentation: { status: "fading" },
    });
    expect(completed).toHaveBeenCalledOnce();
  });

  it("uses guest completion as a fallback readiness signal", () => {
    const completed = vi.fn();
    const { runtime, runs } = guestFixture({
      guestAccess: {
        canSearch: () => true,
        requestSignup: vi.fn(),
        recordCompletedSearch: completed,
      },
    });
    runtime.send({ type: "submit", request: REQUEST });

    runs[0].callbacks.onPassage(passage("p1"));
    expect(() => runs[0].callbacks.onDone(null, 1, "success", { bible: "results" }, true))
      .not.toThrow();

    expect(runtime.read()).toMatchObject({
      transport: { status: "complete", resultCount: 1 },
      presentation: { status: "animating", resultsReady: true },
    });
    expect(completed).toHaveBeenCalledOnce();
    expect(completed).toHaveBeenCalledWith(1);
  });

  it("preserves guest Passages when completion fails after results-ready", () => {
    const { runtime, runs } = guestFixture();
    runtime.send({ type: "submit", request: REQUEST });
    const runId = runtime.read().runId;
    runs[0].callbacks.onPassage(passage("p1"));
    runs[0].callbacks.onResultsReady(1);
    runs[0].callbacks.onError("Transfer finalization failed", "transfer_failed", "transfer");

    expect(runtime.read()).toMatchObject({
      status: "active-search",
      transport: {
        status: "ranked-ready",
        completionFailure: { code: "transfer_failed", stage: "transfer" },
      },
      presentation: { resultsReady: true },
      passages: [],
    });

    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });
    expect(runtime.read()).toMatchObject({
      status: "active-search",
      passages: [{ chunk_id: "p1" }],
      presentation: { status: "fading" },
    });
  });

  it("preserves revealed guest Passages after a late rate-limit callback", () => {
    const { runtime, runs } = guestFixture();
    runtime.send({ type: "submit", request: REQUEST });
    const runId = runtime.read().runId;
    runs[0].callbacks.onPassage(passage("p1"));
    runs[0].callbacks.onResultsReady(1);
    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });

    runs[0].callbacks.onRateLimit(30, "per_minute");
    expect(runtime.read()).toMatchObject({
      status: "active-search",
      transport: {
        status: "ranked-ready",
        completionFailure: { code: "rate_limit", stage: "rate_limit" },
      },
      passages: [{ chunk_id: "p1" }],
      presentation: { status: "fading" },
    });
  });

  it("opens signup instead of exposing trial exhaustion as a search failure", () => {
    const requestSignup = vi.fn();
    const { runtime, runs } = guestFixture({
      guestAccess: {
        canSearch: () => true,
        requestSignup,
        recordCompletedSearch: vi.fn(),
      },
    });
    runtime.send({ type: "submit", request: REQUEST });

    runs[0].callbacks.onError("trial_exhausted", "rate_limit", "rate_limit");

    expect(requestSignup).toHaveBeenCalledWith("limit");
    expect(runtime.read()).toMatchObject({ status: "idle" });
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

  it("invalidates ownership before synchronous abort callbacks and serializes reentrant commands", () => {
    const failed = vi.fn();
    const runs: ScriptedRun[] = [];
    const runtimeRef: { current: ReturnType<typeof createSearchExperience> | null } = { current: null };
    const audience: Extract<AudienceAdapter, { kind: "authenticated" }> = {
      kind: "authenticated",
      search(credential, request, callbacks, signal) {
        runs.push({ credential, request, callbacks, signal });
        signal.addEventListener("abort", () => {
          callbacks.onError("cancelled synchronously", "cancelled", "abort");
          if (request.query === "First") {
            runtimeRef.current!.send({ type: "submit", request: { ...REQUEST, query: "Reentrant" } });
          }
        });
        return Promise.resolve();
      },
    };
    const runtime = createSearchExperience({
      audience,
      credentials: { current: () => "token" },
      analytics: { searchCompleted: vi.fn(), searchFailed: failed },
    });
    runtimeRef.current = runtime;

    runtime.send({ type: "submit", request: { ...REQUEST, query: "First" } });
    runtime.send({ type: "submit", request: { ...REQUEST, query: "Second" } });

    expect(runs).toHaveLength(3);
    expect(runs[0].signal.aborted).toBe(true);
    expect(runs[1].signal.aborted).toBe(true);
    expect(runs[2].signal.aborted).toBe(false);
    expect(failed).not.toHaveBeenCalled();
    expect(runtime.read()).toMatchObject({
      status: "active-search",
      request: { query: "Reentrant" },
      runId: 3,
    });
  });

  it("aborts across search and restore replacements", () => {
    const restoreSignals: AbortSignal[] = [];
    const savedSearch = {
      restore: vi.fn((_credential: string, _searchId: string, signal: AbortSignal) => {
        restoreSignals.push(signal);
        return new Promise<never>(() => undefined);
      }),
    };
    const { runtime, runs } = authenticatedFixture({ savedSearch });

    runtime.send({ type: "submit", request: REQUEST });
    const searchRunId = runtime.read().runId;
    runtime.send({ type: "restore", searchId: "saved-search" });

    expect(runs[0].signal.aborted).toBe(true);
    expect(runtime.read()).toMatchObject({ status: "restoring", runId: searchRunId + 1 });

    runtime.send({ type: "submit", request: { ...REQUEST, query: "Replacement search" } });
    expect(restoreSignals[0].aborted).toBe(true);
    expect(runtime.read()).toMatchObject({
      status: "active-search",
      runId: searchRunId + 2,
      request: { query: "Replacement search" },
    });
  });

  it("preserves the current guest view when a replacement is denied before transport", () => {
    let canSearch = true;
    const requestSignup = vi.fn();
    const { runtime, runs } = guestFixture({
      guestAccess: {
        canSearch: () => canSearch,
        requestSignup,
        recordCompletedSearch: vi.fn(),
      },
    });

    runtime.send({ type: "submit", request: REQUEST });
    const activeRunId = runtime.read().runId;
    canSearch = false;
    runtime.send({ type: "submit", request: { ...REQUEST, query: "Denied replacement" } });

    expect(runs[0].signal.aborted).toBe(false);
    expect(runs).toHaveLength(1);
    expect(requestSignup).toHaveBeenCalledWith("limit");
    expect(runtime.read()).toMatchObject({ status: "active-search", runId: activeRunId });
  });

  it("cancels the current run before a restore fails for missing credentials", () => {
    let credential: string | null = "current-token";
    const savedSearch = { restore: vi.fn() };
    const { runtime, runs } = authenticatedFixture({
      credentials: { current: () => credential },
      savedSearch,
    });

    runtime.send({ type: "submit", request: REQUEST });
    const activeRunId = runtime.read().runId;
    credential = null;
    runtime.send({ type: "restore", searchId: "saved-search" });

    expect(runs[0].signal.aborted).toBe(true);
    expect(savedSearch.restore).not.toHaveBeenCalled();
    expect(runtime.read()).toMatchObject({
      status: "failure",
      runId: activeRunId + 1,
      restoreId: "saved-search",
      failure: { kind: "restore", code: "auth_error" },
      canRetry: false,
    });
  });

  it("turns synchronous credential and search adapter throws into failure snapshots", () => {
    const credentialFailure = createSearchExperience({
      audience: {
        kind: "authenticated",
        search: () => Promise.resolve(),
      },
      credentials: { current: () => { throw new Error("credential exploded"); } },
    });
    expect(() => credentialFailure.send({ type: "submit", request: REQUEST })).not.toThrow();
    expect(credentialFailure.read()).toMatchObject({
      status: "failure",
      failure: { message: "credential exploded", stage: "connection" },
    });

    const searchFailure = createSearchExperience({
      audience: {
        kind: "authenticated",
        search: () => { throw new Error("search exploded"); },
      },
      credentials: { current: () => "token" },
    });
    expect(() => searchFailure.send({ type: "submit", request: REQUEST })).not.toThrow();
    expect(searchFailure.read()).toMatchObject({
      status: "failure",
      failure: { message: "search exploded", stage: "connection" },
    });
  });

  it("turns a synchronous guest-access throw into a failure snapshot", () => {
    const { runtime } = guestFixture({
      guestAccess: {
        canSearch: () => { throw new Error("guest access exploded"); },
        requestSignup: vi.fn(),
        recordCompletedSearch: vi.fn(),
      },
    });

    expect(() => runtime.send({ type: "submit", request: REQUEST })).not.toThrow();
    expect(runtime.read()).toMatchObject({
      status: "failure",
      failure: { message: "guest access exploded", stage: "guest_access" },
    });
  });

  it("turns synchronous restore adapter throws into a failure snapshot", () => {
    const { runtime } = authenticatedFixture({
      savedSearch: {
        restore: () => { throw new Error("restore exploded"); },
      },
    });

    expect(() => runtime.send({ type: "restore", searchId: "saved-search" })).not.toThrow();
    expect(runtime.read()).toMatchObject({
      status: "failure",
      restoreId: "saved-search",
      failure: { message: "restore exploded", stage: "restore" },
    });
  });

  it("uses the saved-search adapter classification and retry rule", async () => {
    const notFound = new Error("request failed");
    const { runtime } = authenticatedFixture({
      savedSearch: {
        restore: async () => { throw notFound; },
        classifyFailure: (error) => {
          expect(error).toBe(notFound);
          return {
            message: "This saved search does not exist.",
            code: "restore_not_found",
            stage: "restore",
            retryable: false,
          };
        },
      },
    });

    runtime.send({ type: "restore", searchId: "saved-search" });
    await Promise.resolve();
    await Promise.resolve();

    expect(runtime.read()).toMatchObject({
      status: "failure",
      failure: {
        message: "This saved search does not exist.",
        code: "restore_not_found",
        stage: "restore",
      },
      canRetry: false,
    });
  });

  it("isolates ID and clock port failures from the lifecycle", () => {
    const begin = vi.fn();
    const { runtime: authenticated, runs } = authenticatedFixture({
      pendingHistory: { begin, clear: vi.fn(), activate: vi.fn(), refresh: vi.fn() },
      ids: { pendingEntry: () => { throw new Error("id exploded"); } },
    });
    authenticated.send({ type: "submit", request: REQUEST });
    const firstRunId = authenticated.read().runId;
    authenticated.send({ type: "submit", request: { ...REQUEST, query: "Replacement" } });
    expect(runs[0].signal.aborted).toBe(true);
    expect(authenticated.read().runId).toBe(firstRunId + 1);
    expect(begin).toHaveBeenLastCalledWith("search-2", "Replacement");

    const save = vi.fn();
    const { runtime: guest, runs: guestRuns } = guestFixture({
      guestContinuity: { save, clear: vi.fn() },
      time: { now: () => { throw new Error("clock exploded"); } },
    });
    guest.send({ type: "submit", request: REQUEST });
    const guestRunId = guest.read().runId;
    guestRuns[0].callbacks.onPassage(passage("p1"));
    guestRuns[0].callbacks.onResultsReady(1);
    guest.send({ type: "animation", runId: guestRunId, milestone: "ready-to-reveal" });
    expect(save).not.toHaveBeenCalled();
    expect(() => guestRuns[0].callbacks.onExplanationDelta("p1", "still streaming")).not.toThrow();
    expect(guest.read()).toMatchObject({ passages: [{ explanation: "still streaming" }] });
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

  it("fails loudly for impossible current-run animation transitions", () => {
    const { runtime, runs } = authenticatedFixture();
    runtime.send({ type: "submit", request: REQUEST });
    const runId = runtime.read().runId;

    expect(() => runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" }))
      .toThrow(/before ranked results are ready/);
    expect(() => runtime.send({ type: "animation", runId, milestone: "fade-complete" }))
      .toThrow(/while the search animation is fading/);

    runtime.send({ type: "animation", runId, milestone: "filters-ready" });
    expect(() => runtime.send({ type: "animation", runId, milestone: "filters-ready" }))
      .toThrow(/must occur once/);

    runs[0].callbacks.onDone("search-1", 0, "no_candidates", {}, true);
    runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" });
    expect(() => runtime.send({ type: "animation", runId, milestone: "ready-to-reveal" }))
      .toThrow(/while the search animation is running/);
    runtime.send({ type: "animation", runId, milestone: "fade-complete" });
    expect(() => runtime.send({ type: "animation", runId, milestone: "fade-complete" }))
      .toThrow(/while the search animation is fading/);
  });

  it("keeps authenticated and guest capabilities mutually exclusive", () => {
    type AuthenticatedAdapter = Extract<AudienceAdapter, { kind: "authenticated" }>;
    type GuestAdapter = Extract<AudienceAdapter, { kind: "guest" }>;

    expectTypeOf<{
      audience: GuestAdapter;
      credentials: { current: () => string };
    }>().not.toMatchTypeOf<SearchExperiencePorts>();
    expectTypeOf<{
      audience: GuestAdapter;
      savedSearch: { restore: () => Promise<never> };
    }>().not.toMatchTypeOf<SearchExperiencePorts>();
    expectTypeOf<{
      audience: AuthenticatedAdapter;
      credentials: { current: () => string };
      guestAccess: { canSearch: () => true };
    }>().not.toMatchTypeOf<SearchExperiencePorts>();

    const guestAudience: GuestAdapter = {
      kind: "guest",
      async search() {},
    };
    expect(() => createSearchExperience({
      audience: guestAudience,
      credentials: { current: () => "token" },
    } as unknown as SearchExperiencePorts)).toThrow(/authenticated capabilities/);
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
      pendingHistory: { begin, clear, activate: vi.fn(), refresh },
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
    expect(clear.mock.invocationCallOrder.at(-1)).toBeLessThan(refresh.mock.invocationCallOrder[0]);
  });

  it("owns the pending History placeholder through submit, completion, and reset", () => {
    const begin = vi.fn();
    const clear = vi.fn();
    const activate = vi.fn();
    const refresh = vi.fn();
    let id = 0;
    const { runtime, runs } = authenticatedFixture({
      pendingHistory: { begin, clear, activate, refresh },
      ids: { pendingEntry: () => `pending-${++id}` },
    });

    runtime.send({ type: "prepare-pending-history" });
    expect(begin).toHaveBeenLastCalledWith("pending-1", "New Search");

    runtime.send({ type: "submit", request: REQUEST });
    expect(begin).toHaveBeenLastCalledWith("pending-1", REQUEST.query);
    runs[0].callbacks.onDone("search-1", 1, "success", {}, true);
    expect(clear).toHaveBeenCalledWith("pending-1");
    expect(activate).toHaveBeenCalledWith("search-1");
    expect(refresh).toHaveBeenCalledOnce();

    runtime.send({ type: "reset" });
    expect(begin).toHaveBeenLastCalledWith("pending-2", "New Search");
  });

  it("owns delayed guest explore submission and cancellation", () => {
    vi.useFakeTimers();
    try {
      const { runtime, runs } = guestFixture();
      const exploreRequest = { ...REQUEST, origin: "explore" as const };

      runtime.send({ type: "queue-explore", request: exploreRequest });
      vi.advanceTimersByTime(299);
      expect(runs).toHaveLength(0);
      runtime.send({ type: "cancel-queued-explore" });
      vi.advanceTimersByTime(1);
      expect(runs).toHaveLength(0);

      runtime.send({ type: "queue-explore", request: exploreRequest });
      vi.advanceTimersByTime(300);
      expect(runs).toHaveLength(1);
      expect(runs[0].request).toEqual(exploreRequest);
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears pending History for failures and rate limits before retrying with a new owner", () => {
    const clear = vi.fn();
    let id = 0;
    const { runtime, runs } = authenticatedFixture({
      pendingHistory: { begin: vi.fn(), clear, activate: vi.fn(), refresh: vi.fn() },
      ids: { pendingEntry: () => `pending-${++id}` },
    });

    runtime.send({ type: "submit", request: REQUEST });
    runs[0].callbacks.onError("Retrieval failed", "retrieval_failed", "retrieval");
    expect(clear).toHaveBeenLastCalledWith("pending-1");

    runtime.send({ type: "retry" });
    runs[1].callbacks.onRateLimit(null, "daily");
    expect(clear).toHaveBeenLastCalledWith("pending-2");
    expect(clear).toHaveBeenCalledTimes(2);
  });

  it("clears each pending History owner on cancel, reset, identity change, and disposal", () => {
    const clear = vi.fn();
    let id = 0;
    const { runtime } = authenticatedFixture({
      pendingHistory: { begin: vi.fn(), clear, activate: vi.fn(), refresh: vi.fn() },
      ids: { pendingEntry: () => `pending-${++id}` },
    });

    runtime.send({ type: "submit", request: REQUEST });
    runtime.send({ type: "cancel" });
    runtime.send({ type: "submit", request: REQUEST });
    runtime.send({ type: "reset" });
    runtime.send({ type: "submit", request: REQUEST });
    runtime.send({ type: "identity-changed", userId: "different-user" });
    runtime.send({ type: "submit", request: REQUEST });
    runtime.send({ type: "dispose" });

    expect(clear.mock.calls).toEqual([
      ["pending-1"],
      ["pending-2"],
      ["pending-3"],
      ["pending-4"],
    ]);
  });

  it("does not let secondary adapter failures discard available Passages", async () => {
    const rejects = () => Promise.reject(new Error("secondary failed"));
    const { runtime, runs } = authenticatedFixture({
      pendingHistory: { begin: rejects, clear: rejects, activate: rejects, refresh: rejects },
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

  it("restores guest continuity on creation and clears it on reset", () => {
    const clear = vi.fn();
    const runtime = createSearchExperience({
      audience: { kind: "guest", async search() {} },
      guestContinuity: {
        restore: () => ({
          savedAt: 1234,
          request: REQUEST,
          searchId: "guest-search",
          passages: [passage("p1")],
          outcome: "success",
          collectionOutcomes: { bible: "results" },
        }),
        save: vi.fn(),
        clear,
      },
    });

    expect(runtime.read()).toMatchObject({
      status: "active-search",
      audience: "guest",
      request: REQUEST,
      transport: { status: "complete", searchId: "guest-search", outcome: "success" },
      presentation: { status: "revealed" },
      passages: [{ chunk_id: "p1" }],
    });

    runtime.send({ type: "reset" });
    expect(clear).toHaveBeenCalledOnce();
    expect(runtime.read()).toMatchObject({ status: "idle" });
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

  it("treats the same saved-search route as one restore until identity changes", async () => {
    const restore = vi.fn(async (_credential: string, searchId: string) => ({
      searchId,
      request: REQUEST,
      passages: [passage("p1")],
      warning: null,
    }));
    const { runtime } = authenticatedFixture({ savedSearch: { restore } });
    runtime.send({ type: "identity-changed", userId: "user-1" });

    runtime.send({ type: "restore", searchId: "saved-search" });
    runtime.send({ type: "restore", searchId: "saved-search" });
    await Promise.resolve();
    runtime.send({ type: "restore", searchId: "saved-search" });

    expect(restore).toHaveBeenCalledOnce();
    expect(runtime.read()).toMatchObject({
      status: "restored-results",
      searchId: "saved-search",
    });

    runtime.send({ type: "identity-changed", userId: "user-2" });
    runtime.send({ type: "restore", searchId: "saved-search" });
    expect(restore).toHaveBeenCalledTimes(2);
  });

  it("reauthorizes only an in-flight restore when credentials rotate", () => {
    let credential = "old-token";
    const restores: Array<{ credential: string; signal: AbortSignal }> = [];
    const { runtime } = authenticatedFixture({
      credentials: { current: () => credential },
      savedSearch: {
        restore: (currentCredential, _searchId, signal) => {
          restores.push({ credential: currentCredential, signal });
          return new Promise<never>(() => undefined);
        },
      },
    });

    runtime.send({ type: "restore", searchId: "saved-search" });
    credential = "rotated-token";
    runtime.send({ type: "credentials-changed" });

    expect(restores).toHaveLength(2);
    expect(restores[0]).toMatchObject({ credential: "old-token" });
    expect(restores[0].signal.aborted).toBe(true);
    expect(restores[1]).toMatchObject({ credential: "rotated-token" });
    expect(restores[1].signal.aborted).toBe(false);
  });

  it("cancels work on identity changes and disposal", () => {
    const { runtime, runs } = authenticatedFixture();
    runtime.send({ type: "identity-changed", userId: "user-1" });
    runtime.send({ type: "submit", request: REQUEST });
    runtime.send({ type: "identity-changed", userId: "user-2" });
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
