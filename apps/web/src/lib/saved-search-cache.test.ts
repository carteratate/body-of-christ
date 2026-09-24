import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SearchResultsResponse } from "@/lib/api";
import { __resetClientCachesForTests } from "./client-cache";
import { evictSavedSearchResults, loadSavedSearchResults, prefetchSavedSearchResults } from "./saved-search-cache";

const api = vi.hoisted(() => ({ getSearchResults: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  getSearchResults: api.getSearchResults,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function results(searchId: string): SearchResultsResponse {
  return { search_id: searchId, query: searchId, results: [] } as unknown as SearchResultsResponse;
}

function jwtForSubject(subject: string, suffix: string): string {
  const payload = btoa(JSON.stringify({ sub: subject })).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `header.${payload}.${suffix}`;
}

beforeEach(() => {
  __resetClientCachesForTests();
  api.getSearchResults.mockReset();
  api.getSearchResults.mockImplementation(async (_token: string, searchId: string) => results(searchId));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("saved-search results cache", () => {
  it("restores from a finished prefetch without another request", async () => {
    prefetchSavedSearchResults("token", "s1", new AbortController().signal);
    await vi.waitFor(() => expect(api.getSearchResults).toHaveBeenCalledTimes(1));
    await Promise.resolve();

    await expect(loadSavedSearchResults("token", "s1")).resolves.toMatchObject({ search_id: "s1" });
    expect(api.getSearchResults).toHaveBeenCalledTimes(1);
  });

  it("joins a prefetch in flight, and survives the prefetch being abandoned", async () => {
    const response = deferred<SearchResultsResponse>();
    let sharedSignal: AbortSignal | undefined;
    api.getSearchResults.mockImplementation((_token: string, _id: string, signal: AbortSignal) => { sharedSignal = signal; return response.promise; });
    const prefetch = new AbortController();

    prefetchSavedSearchResults("token", "s1", prefetch.signal);
    const restore = loadSavedSearchResults("token", "s1");
    prefetch.abort();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sharedSignal?.aborted).toBe(false);
    response.resolve(results("s1"));

    await expect(restore).resolves.toMatchObject({ search_id: "s1" });
    expect(api.getSearchResults).toHaveBeenCalledTimes(1);
  });

  it("gives a restore its own timeout without poisoning the entry", async () => {
    vi.useFakeTimers();
    const response = deferred<SearchResultsResponse>();
    api.getSearchResults.mockReturnValue(response.promise);
    prefetchSavedSearchResults("token", "s1", new AbortController().signal);

    const restore = loadSavedSearchResults("token", "s1");
    const timedOut = expect(restore).rejects.toMatchObject({ name: "TimeoutError", message: "This saved search took too long to load. Please try again." });
    await vi.advanceTimersByTimeAsync(10_000);
    await timedOut;

    response.resolve(results("s1"));
    await vi.advanceTimersByTimeAsync(0);
    await expect(loadSavedSearchResults("token", "s1")).resolves.toMatchObject({ search_id: "s1" });
    expect(api.getSearchResults).toHaveBeenCalledTimes(1);
  });

  it("rejects an aborted restore without cancelling a prefetch other callers share", async () => {
    const response = deferred<SearchResultsResponse>();
    let sharedSignal: AbortSignal | undefined;
    api.getSearchResults.mockImplementation((_token: string, _id: string, signal: AbortSignal) => { sharedSignal = signal; return response.promise; });
    prefetchSavedSearchResults("token", "s1", new AbortController().signal);
    const leaving = new AbortController();

    const restore = loadSavedSearchResults("token", "s1", leaving.signal);
    leaving.abort();

    await expect(restore).rejects.toMatchObject({ name: "AbortError" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sharedSignal?.aborted).toBe(false);
  });

  it("does not remember a failure", async () => {
    api.getSearchResults.mockRejectedValueOnce(new Error("offline"));

    await expect(loadSavedSearchResults("token", "s1")).rejects.toThrow("offline");
    await expect(loadSavedSearchResults("token", "s1")).resolves.toMatchObject({ search_id: "s1" });
    expect(api.getSearchResults).toHaveBeenCalledTimes(2);
  });

  async function prefetched(token: string, searchId: string) {
    prefetchSavedSearchResults(token, searchId, new AbortController().signal);
    await vi.waitFor(() => expect(api.getSearchResults.mock.calls.some((call) => call[0] === token && call[1] === searchId)).toBe(true));
    await Promise.resolve();
    await Promise.resolve();
  }

  it("forgets a prefetch nobody used after a minute", async () => {
    await prefetched("token", "s1");
    vi.useFakeTimers();

    vi.advanceTimersByTime(60_000);
    await loadSavedSearchResults("token", "s1");

    expect(api.getSearchResults).toHaveBeenCalledTimes(2);
  });

  it("is consumed by a restore, so restoring again reads the server", async () => {
    await loadSavedSearchResults("token", "s1");
    await loadSavedSearchResults("token", "s1");

    expect(api.getSearchResults).toHaveBeenCalledTimes(2);
  });

  it("forgets a deleted search", async () => {
    await prefetched("token", "s1");
    await prefetched("token", "s2");

    evictSavedSearchResults("s1");
    await loadSavedSearchResults("token", "s1");
    await loadSavedSearchResults("token", "s2");

    expect(api.getSearchResults.mock.calls.map((call) => call[1])).toEqual(["s1", "s2", "s1"]);
  });

  it("keeps each user's results apart and survives a token refresh", async () => {
    await prefetched(jwtForSubject("user-1", "a"), "s1");
    await loadSavedSearchResults(jwtForSubject("user-2", "a"), "s1");
    await loadSavedSearchResults(jwtForSubject("user-1", "b"), "s1");

    expect(api.getSearchResults).toHaveBeenCalledTimes(2);
  });
});
