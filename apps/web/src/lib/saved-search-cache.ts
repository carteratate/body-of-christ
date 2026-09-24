// Saved-search results fetched ahead of a restore.
//
// Hovering or focusing a History row warms its results, so the click that
// follows restores from memory instead of paying a round trip. This sits under
// the search-experience runtime's savedSearch port: the runtime still owns the
// restore, and a prefetch can neither activate pending history nor fire
// analytics. Entries live for a minute; the aim is hover-to-click latency, not
// a second copy of history.
//
// Entries are keyed by user, and a restore keeps its own abort signal and
// ten-second timeout even when it joins a prefetch already in flight. A restore
// consumes its entry, so restoring the same search again goes to the server as
// it always did; only a prefetch nobody clicked stays for the minute.

import { getSearchResults, userScope, type SearchResultsResponse } from "@/lib/api";
import { createRequestCache } from "@/lib/client-cache";

const RESULTS_TTL_MS = 60_000;
const RESULTS_CACHE_SIZE = 10;
const RESTORE_TIMEOUT_MS = 10_000;
// Backstop for the shared request itself; each restore enforces its own
// shorter timeout from when it started waiting.
const SHARED_REQUEST_TIMEOUT_MS = 30_000;

const resultsCache = createRequestCache<SearchResultsResponse>({ maxEntries: RESULTS_CACHE_SIZE, ttlMs: RESULTS_TTL_MS });

function cacheKey(token: string, searchId: string): string {
  return `${userScope(token)}\n${searchId}`;
}

function load(token: string, searchId: string, signal?: AbortSignal): Promise<SearchResultsResponse> {
  return resultsCache.get(
    cacheKey(token, searchId),
    (shared) => getSearchResults(token, searchId, shared, SHARED_REQUEST_TIMEOUT_MS),
    signal,
  );
}

export async function loadSavedSearchResults(
  token: string,
  searchId: string,
  signal?: AbortSignal,
  timeoutMs = RESTORE_TIMEOUT_MS,
): Promise<SearchResultsResponse> {
  const waiter = new AbortController();
  let timedOut = false;
  const forwardAbort = () => waiter.abort(signal?.reason);
  if (signal?.aborted) forwardAbort();
  else signal?.addEventListener("abort", forwardAbort, { once: true });
  const timeout = setTimeout(() => {
    timedOut = true;
    waiter.abort();
  }, timeoutMs);
  try {
    const results = await load(token, searchId, waiter.signal);
    resultsCache.evict(cacheKey(token, searchId));
    return results;
  } catch (error) {
    if (timedOut) {
      const timeoutError = new Error("This saved search took too long to load. Please try again.");
      timeoutError.name = "TimeoutError";
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", forwardAbort);
  }
}

export function prefetchSavedSearchResults(token: string, searchId: string, signal: AbortSignal): void {
  load(token, searchId, signal).catch(() => undefined);
}

export function evictSavedSearchResults(searchId: string): void {
  resultsCache.evictWhere((key) => key.endsWith(`\n${searchId}`));
}
