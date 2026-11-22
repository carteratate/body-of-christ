"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  SearchRestoreHttpError,
  streamGuestSearch,
  streamSearch,
  type CollectionOutcome,
  type DeliveryOutcome,
  type SearchFilters,
  type SearchOutcome,
  type SearchResultsResponse,
} from "@/lib/api";
import { trackErrorOccurred, trackSearchPerformed } from "@/lib/analytics";
import {
  canonicalSearchFilters, parseScopeSelections, type ScopeSelection,
} from "@/lib/collection-scopes";
import { ALL_COLLECTION_KEYS, canonicalCollectionKey } from "@/lib/collections";
import { loadSavedSearchResults } from "@/lib/saved-search-cache";
import {
  isDeliveryOutcome,
  isSearchOutcome,
  parseCollectionOutcomes,
} from "@/lib/search-stream";
import { getGuestSessionToken, GUEST_SEARCH_LIMIT } from "@/lib/trial";
import { classifySearchErrorCode } from "./failure";
import { createSearchExperience } from "./runtime";
import type {
  AuthenticatedSearchExperiencePorts,
  GuestContinuitySnapshot,
  Passage,
  SearchExperience,
  SearchRequest,
  SearchTransportCallbacks,
} from "./types";
import { useSearchExperience } from "./useSearchExperience";
import { currentSearchId, searchExperienceView } from "./view";

const GUEST_CONTINUITY_KEY = "theocorpus-guest-current-results";
const GUEST_CONTINUITY_MAX_AGE_MS = 2 * 60 * 60 * 1000;

interface GuestContinuityStorage {
  savedAt: number;
  query: string;
  passages: Passage[];
  searchId: string | null;
  collections: string[];
  translation: string;
  quota: number;
  visibleCollections: string[];
  outcome: SearchOutcome | null;
  collectionOutcomes: Record<string, CollectionOutcome>;
  deliveryOutcome?: DeliveryOutcome | null;
  scopes?: Record<string, ScopeSelection>;
}

export interface RestoredGuestSearch {
  readonly continuity: GuestContinuitySnapshot;
  readonly visibleCollections: readonly string[];
}

export function readGuestSearch(): RestoredGuestSearch | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(GUEST_CONTINUITY_KEY) ?? "null") as Record<string, unknown> | null;
    const passages = Array.isArray(value?.passages)
      ? value.passages
      : Array.isArray(value?.results) ? value.results : null;
    if (!value || typeof value.savedAt !== "number"
      || Date.now() - value.savedAt > GUEST_CONTINUITY_MAX_AGE_MS) return null;
    if (typeof value.query !== "string" || !passages
      || !Array.isArray(value.collections)) return null;
    if (typeof value.translation !== "string" || typeof value.quota !== "number"
      || !Array.isArray(value.visibleCollections)) return null;
    const snapshot = value as unknown as Omit<GuestContinuityStorage, "passages">;
    // A search saved by the page before 5.1b.2 carries old collection keys.
    const filters = canonicalSearchFilters(snapshot.collections, snapshot.scopes);
    const collections = filters.collections.filter((c) => ALL_COLLECTION_KEYS.includes(c));
    const scopes = parseScopeSelections(filters.scopes, collections);
    const visibleCollections = canonicalKeys(snapshot.visibleCollections);
    return {
      continuity: {
        savedAt: snapshot.savedAt,
        request: {
          query: snapshot.query,
          collections,
          translation: snapshot.translation,
          quota: snapshot.quota,
          ...(scopes ? { scopes } : {}),
        },
        searchId: snapshot.searchId,
        passages: (passages as Passage[]).map(canonicalPassage),
        outcome: snapshot.outcome,
        collectionOutcomes: canonicalOutcomes(snapshot.collectionOutcomes) ?? {},
        deliveryOutcome: isDeliveryOutcome(snapshot.deliveryOutcome)
          ? snapshot.deliveryOutcome : null,
        visibleCollections,
      },
      visibleCollections,
    };
  } catch {
    return null;
  }
}

function canonicalKeys(keys: readonly unknown[]): string[] {
  return [...new Set(keys.filter((k): k is string => typeof k === "string").map(canonicalCollectionKey))];
}

/** A passage labelled in today's vocabulary: a saved search's passages carry the key it
 * was searched under, an old one for a search made before 5.1b.2. */
export function canonicalPassage<T extends { readonly source: { readonly collection: string } }>(passage: T): T {
  const collection = canonicalCollectionKey(passage.source.collection);
  return collection === passage.source.collection
    ? passage : { ...passage, source: { ...passage.source, collection } };
}

// Most informative first, when several old keys become one collection: any results
// beat none, and a failure is worth reporting over an empty search.
const OUTCOME_ORDER: readonly CollectionOutcome[] = [
  "results", "results_degraded", "retrieval_failed", "corpus_sync_failed",
  "ranking_failed", "below_threshold", "no_candidates",
];
const OUTCOME_FAILURES = new Set<CollectionOutcome>([
  "results_degraded", "retrieval_failed", "corpus_sync_failed", "ranking_failed",
]);

/**
 * Per-collection outcomes in today's vocabulary. Old keys that became one collection
 * merge: results if any had results (degraded if another failed or was degraded),
 * otherwise the most informative of their outcomes.
 */
export function canonicalOutcomes(
  outcomes: Readonly<Record<string, CollectionOutcome>> | null | undefined,
): Record<string, CollectionOutcome> | null {
  if (!outcomes) return null;
  const grouped = new Map<string, CollectionOutcome[]>();
  for (const [key, outcome] of Object.entries(outcomes)) {
    const canonical = canonicalCollectionKey(key);
    grouped.set(canonical, [...(grouped.get(canonical) ?? []), outcome]);
  }
  return Object.fromEntries([...grouped].map(([key, values]) => {
    const found = values.some((v) => v === "results" || v === "results_degraded");
    if (found) {
      return [key, values.some((v) => OUTCOME_FAILURES.has(v)) ? "results_degraded" : "results"];
    }
    return [key, OUTCOME_ORDER.find((o) => values.includes(o)) ?? values[0]];
  }));
}

function clearGuestSearch() {
  try { sessionStorage.removeItem(GUEST_CONTINUITY_KEY); } catch {}
}

export function saveGuestSearch(continuity: GuestContinuitySnapshot) {
  const snapshot: GuestContinuityStorage = {
    savedAt: continuity.savedAt,
    query: continuity.request.query,
    passages: [...continuity.passages],
    searchId: continuity.searchId,
    collections: [...continuity.request.collections],
    translation: continuity.request.translation,
    quota: continuity.request.quota,
    visibleCollections: [...(continuity.visibleCollections ?? continuity.request.collections)],
    outcome: continuity.outcome,
    collectionOutcomes: { ...continuity.collectionOutcomes },
    deliveryOutcome: continuity.deliveryOutcome ?? null,
    ...(continuity.request.scopes
      ? { scopes: continuity.request.scopes as Record<string, ScopeSelection> } : {}),
  };
  try { sessionStorage.setItem(GUEST_CONTINUITY_KEY, JSON.stringify(snapshot)); } catch {}
}

/** The request's filters as the API takes them; `scopes` only when something narrows. */
export function filtersFor(request: SearchRequest): SearchFilters {
  return {
    collections: [...request.collections],
    translation: request.translation,
    // The runtime froze its own copy; the transport only serialises it.
    ...(request.scopes ? { scopes: request.scopes as Record<string, ScopeSelection> } : {}),
  };
}

/**
 * The request a saved search was made with, read from its stored filters: the
 * collections, translation, quota and genre and issuer selection it asked for, with
 * today's settings where a field is missing or invalid.
 */
export function savedSearchRequest(
  data: Pick<SearchResultsResponse, "query" | "filters" | "results">,
  fallback: { readonly storedCollections?: unknown; readonly translation: string; readonly quota: number },
): SearchRequest {
  const responseCollections = data.filters?.collections;
  const storedCollections = Array.isArray(responseCollections)
    ? responseCollections
    : fallback.storedCollections;
  // Old keys become new ones; an old papal key becomes a Papal documents genre selection.
  const filters = canonicalSearchFilters(
    Array.isArray(storedCollections) ? storedCollections : [], data.filters?.scopes);
  const askedCollections = filters.collections.filter((c) => ALL_COLLECTION_KEYS.includes(c));
  const collections = askedCollections.length > 0
    ? askedCollections
    : canonicalKeys(data.results.map((passage) => passage.source.collection));
  const translation = typeof data.filters?.translation === "string" && data.filters.translation
    ? data.filters.translation
    : fallback.translation;
  const savedQuota = data.filters?.quota;
  const quota = typeof savedQuota === "number"
    && ([3, 4, 5].includes(savedQuota) || (savedQuota === 10 && collections.length === 1))
    ? savedQuota
    : fallback.quota;
  const scopes = parseScopeSelections(filters.scopes, collections);
  return {
    query: data.query,
    collections,
    translation,
    quota,
    ...(scopes ? { scopes } : {}),
  };
}

class InvalidSavedSearchIdError extends Error {}
class SavedPassagesUnavailableError extends Error {}

function classifySavedSearchFailure(error: unknown) {
  if (error instanceof InvalidSavedSearchIdError) {
    return {
      message: "This saved search link is invalid.",
      code: "restore_not_found",
      stage: "restore",
      retryable: false,
    } as const;
  }
  if (error instanceof SavedPassagesUnavailableError) {
    return {
      message: error.message,
      code: "restore_unavailable",
      stage: "restore",
      retryable: false,
    } as const;
  }
  if (error instanceof SearchRestoreHttpError) {
    if (error.status === 401 || error.status === 403) {
      return {
        message: error.message,
        code: "auth_error",
        stage: "authentication",
        retryable: false,
      } as const;
    }
    if (error.status === 404) {
      return {
        message: error.message,
        code: "restore_not_found",
        stage: "restore",
        retryable: false,
      } as const;
    }
  }
  const message = error instanceof Error ? error.message : "Failed to restore search";
  return {
    message,
    code: error instanceof Error && error.name === "TimeoutError"
      ? "network_error"
      : classifySearchErrorCode(message),
    stage: "restore",
    retryable: true,
  } as const;
}

const searchAnalytics: NonNullable<AuthenticatedSearchExperiencePorts["analytics"]> = {
  searchCompleted({ request, resultCount }) {
    trackSearchPerformed({
      queryLength: request.query.length,
      collectionsUsed: [...request.collections],
      quotaPerSource: request.quota,
      resultCount,
      translation: request.translation,
    });
  },
  searchFailed({ code }) {
    if (code === "rate_limit") return;
    const errorType = code === "auth_error" || code === "network_error"
      ? code
      : "server_error";
    trackErrorOccurred({ page: "search", errorType });
  },
};

function adaptTransportCallbacks(callbacks: SearchTransportCallbacks) {
  return {
    onStatus: callbacks.onStatus,
    onChunk: callbacks.onPassage,
    onResultsReady: callbacks.onPassagesReady,
    onExplanationDelta: callbacks.onExplanationDelta,
    onDone: callbacks.onDone,
    onError: callbacks.onError,
    onRateLimit: callbacks.onRateLimit,
  };
}

interface SearchSummary {
  readonly id: string;
  readonly filters?: { readonly collections?: readonly string[] } | null;
}

interface GuestGate {
  readonly searchCount: number;
  readonly requestSignup: (reason: "limit") => void;
  readonly recordCompletedSearch: () => void;
}

interface PagePendingHistory {
  readonly showPending: (entryId: string, query: string) => void;
  readonly clearPending: (entryId: string) => void;
  /** Receives `currentSearchId` (view.ts) whenever it changes. */
  readonly showCurrent: (searchId: string | null) => void;
  readonly refresh: () => void;
}

interface SearchPageViewSynchronization {
  readonly setVisibleCollections: (collections: string[]) => void;
  readonly clearDraft: () => void;
}

interface SearchPageExperienceOptions {
  readonly isGuest: boolean;
  readonly token: string | null;
  readonly userId: string | null;
  readonly searches: readonly SearchSummary[];
  readonly translation: string;
  readonly quota: number;
  readonly restoredGuestSearch: RestoredGuestSearch | null;
  readonly guestGate: GuestGate | null;
  readonly pendingHistory: PagePendingHistory;
  readonly viewSynchronization: SearchPageViewSynchronization;
  readonly onFirstGuestSearchWithPassages: () => void;
  /**
   * Where AppShell keeps the authenticated runtime between visits to the search
   * page. Without one (guests, isolated tests) the runtime lives and dies with
   * the page.
   */
  readonly slot?: SearchExperienceSlot | null;
}

export interface SearchPageExperienceBinding {
  readonly experience: SearchExperience;
  readonly read: () => SearchPageExperienceOptions;
  readonly update: (next: SearchPageExperienceOptions) => void;
  /** The result filter the reader chose for a run, kept so a page returning to
   *  that run shows the same filter. */
  readonly visibleFor: (runId: number) => readonly string[] | null;
  readonly rememberVisible: (runId: number, collections: readonly string[]) => void;
}

/** AppShell's holder for the signed-in search runtime; see `slot` above. */
export interface SearchExperienceSlot {
  current: SearchPageExperienceBinding | null;
  /** AppShell's live token. The runtime outlives the page whose options it
   *  holds, so it must not read a token captured by that page's last render. */
  token: string | null;
}

export function createSearchExperienceSlot(): SearchExperienceSlot {
  return { current: null, token: null };
}

export function setSearchExperienceSlotToken(slot: SearchExperienceSlot, token: string | null) {
  slot.token = token;
}

/** Reset the held runtime for New Search, if a search page has created one. */
export function resetSearchExperienceSlot(slot: SearchExperienceSlot) {
  slot.current?.experience.send({ type: "reset" });
}

/** End the held runtime: on sign-out or when AppShell unmounts. */
export function disposeSearchExperienceSlot(slot: SearchExperienceSlot) {
  const binding = slot.current;
  slot.current = null;
  binding?.experience.send({ type: "dispose" });
}

function createSearchPageExperience(options: SearchPageExperienceOptions): SearchPageExperienceBinding {
  let current = options;
  let visible: { readonly runId: number; readonly collections: readonly string[] } | null = null;
  const experience = (() => {
    if (options.isGuest) {
      return createSearchExperience({
        audience: {
          kind: "guest",
          search: (request, callbacks, signal) => streamGuestSearch(
            getGuestSessionToken(),
            request.query,
            filtersFor(request),
            request.quota,
            adaptTransportCallbacks(callbacks),
            signal,
          ),
        },
        guestAccess: {
          canSearch: () => (current.guestGate?.searchCount ?? 0) < GUEST_SEARCH_LIMIT,
          requestSignup: (reason) => current.guestGate?.requestSignup(reason),
          recordCompletedSearch(resultCount) {
            const gate = current.guestGate;
            const completedNumber = (gate?.searchCount ?? 0) + 1;
            gate?.recordCompletedSearch();
            if (completedNumber === 1 && resultCount > 0) {
              current.onFirstGuestSearchWithPassages();
            }
          },
        },
        guestContinuity: {
          restore: () => current.restoredGuestSearch?.continuity ?? null,
          save: saveGuestSearch,
          clear: clearGuestSearch,
        },
        time: { now: Date.now },
        analytics: searchAnalytics,
      });
    }

    return createSearchExperience({
      audience: {
        kind: "authenticated",
        search: (credential, request, callbacks, signal) => streamSearch(
          credential,
          request.query,
          filtersFor(request),
          request.quota,
          adaptTransportCallbacks(callbacks),
          signal,
        ),
      },
      credentials: { current: () => current.slot?.token ?? current.token },
      savedSearch: {
        async restore(credential, searchId, signal) {
          const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
          if (!UUID_RE.test(searchId)) throw new InvalidSavedSearchIdError(searchId);
          const data = await loadSavedSearchResults(credential, searchId, signal);
          if (data.restore_status === "results_unavailable" && data.results.length === 0) {
            throw new SavedPassagesUnavailableError(
              "None of the Passages linked to this saved search remain available.",
            );
          }
          const request = savedSearchRequest(data, {
            storedCollections: current.searches.find((search) => search.id === searchId)?.filters?.collections,
            translation: current.translation,
            quota: current.quota,
          });
          const { collections, quota } = request;
          const deliveryOutcome = quota === 10 && isDeliveryOutcome(data.delivery_outcome)
            ? data.delivery_outcome : null;
          const outcome = isSearchOutcome(data.outcome) ? data.outcome : null;
          const parsedCollectionOutcomes = canonicalOutcomes(
            parseCollectionOutcomes(data.collection_outcomes));
          const collectionOutcomes = parsedCollectionOutcomes
            ? Object.fromEntries(
                Object.entries(parsedCollectionOutcomes)
                  .filter(([collection]) => collections.includes(collection)),
              )
            : {};
          return {
            searchId: data.search_id,
            request,
            // A null explanation in a saved search is one the stream never reached
            // (the page left before it was written). The card reads null as "still
            // streaming", so hide it instead of showing a skeleton that never fills.
            passages: data.results.map((saved) => {
              const passage = canonicalPassage(saved);
              return passage.explanation === null ? { ...passage, explanation: "" } : passage;
            }),
            warning: data.restore_status === "results_unavailable"
              ? `This saved search originally had ${data.expected_result_count} Passages, but only ${data.results.length} remain available.`
              : null,
            outcome,
            collectionOutcomes,
            deliveryOutcome,
            originalResultCount: data.expected_result_count,
            historicalOutcomeUnknown: quota === 10 && deliveryOutcome === null,
          };
        },
        classifyFailure: classifySavedSearchFailure,
      },
      pendingHistory: {
        begin(entryId, query) {
          current.pendingHistory.showPending(entryId, query);
        },
        clear(entryId) {
          current.pendingHistory.clearPending(entryId);
        },
        refresh: () => current.pendingHistory.refresh(),
      },
      ids: { pendingEntry: () => crypto.randomUUID() },
      analytics: searchAnalytics,
    });
  })();

  if (!options.isGuest) {
    // History's "Current" marker is derived from the snapshot, never set by hand,
    // so it always names the search the page would show on return.
    let shown: string | null = null;
    experience.subscribe(() => {
      const next = currentSearchId(experience.read());
      if (next === shown) return;
      shown = next;
      current.pendingHistory.showCurrent(next);
    });
  }

  return {
    experience,
    read: () => current,
    update(next: SearchPageExperienceOptions) { current = next; },
    visibleFor: (runId) => (visible?.runId === runId ? visible.collections : null),
    rememberVisible(runId, collections) { visible = { runId, collections: [...collections] }; },
  };
}

export function useSearchPageExperience(options: SearchPageExperienceOptions) {
  const slot = options.isGuest ? null : options.slot ?? null;
  const [pageBinding] = useState(() => (slot ? null : createSearchPageExperience(options)));
  // Read the slot on every render rather than once: if its runtime was disposed
  // and replaced (AppShell remounting under Fast Refresh), bind to the new one.
  const binding = pageBinding ?? (slot!.current ??= createSearchPageExperience(options));
  useLayoutEffect(() => { binding.update(options); }, [binding, options]);

  const snapshot = useSearchExperience(binding.experience, { disposeOnRelease: !slot });
  const view = searchExperienceView(snapshot);
  // A held runtime may be mid-animation from an earlier visit; this page's
  // LoadingAnimation starts over, so let the runtime catch it up first.
  useLayoutEffect(() => {
    binding.experience.send({ type: "resume-presentation" });
  }, [binding]);
  useEffect(() => {
    if (!slot) return;
    return () => binding.experience.send({ type: "detach-page" });
  }, [binding, slot]);
  useLayoutEffect(() => {
    if (options.isGuest) return;
    binding.experience.send({ type: "identity-changed", userId: options.userId });
  }, [binding, options.isGuest, options.userId]);

  const synchronizedRun = useRef<number | null>(
    options.isGuest && options.restoredGuestSearch ? snapshot.runId : null,
  );
  useLayoutEffect(() => {
    const synchronization = binding.read().viewSynchronization;
    // A run the reader already filtered (before leaving the page) keeps that filter.
    const visibleFor = (runId: number, collections: readonly string[]) =>
      [...(binding.visibleFor(runId) ?? collections)];
    if (view.active && synchronizedRun.current !== view.active.runId) {
      synchronizedRun.current = view.active.runId;
      synchronization.setVisibleCollections(visibleFor(view.active.runId, view.active.request.collections));
      return;
    }
    if (options.isGuest) return;
    if (view.restored && synchronizedRun.current !== view.restored.runId) {
      synchronizedRun.current = view.restored.runId;
      synchronization.setVisibleCollections(visibleFor(view.restored.runId, view.restored.request.collections));
      return;
    }
    if (view.restoring || view.failure?.failure.kind === "restore") {
      synchronization.setVisibleCollections([]);
      if (view.restoring) synchronization.clearDraft();
    }
  }, [binding, options.isGuest, snapshot.runId, view.active, view.failure?.failure.kind, view.restored, view.restoring]);

  const rememberVisibleCollections = useCallback((collections: readonly string[]) => {
    binding.rememberVisible(binding.experience.read().runId, collections);
  }, [binding]);

  return { experience: binding.experience, snapshot, view, rememberVisibleCollections };
}
