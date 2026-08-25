"use client";

import { useLayoutEffect, useState } from "react";

import {
  getSearchResults,
  SearchRestoreHttpError,
  streamGuestSearch,
  streamSearch,
  type ChunkResult,
  type CollectionOutcome,
  type SearchOutcome,
} from "@/lib/api";
import { trackErrorOccurred, trackSearchPerformed } from "@/lib/analytics";
import { ALL_COLLECTION_KEYS } from "@/lib/collections";
import { getGuestSessionToken, GUEST_SEARCH_LIMIT } from "@/lib/trial";
import { createSearchExperience } from "./runtime";
import type {
  AuthenticatedSearchExperiencePorts,
  GuestContinuitySnapshot,
} from "./types";
import { useSearchExperience } from "./useSearchExperience";

const GUEST_RESULTS_KEY = "theocorpus-guest-current-results";
const GUEST_RESULTS_MAX_AGE_MS = 2 * 60 * 60 * 1000;

interface GuestResultsSnapshot {
  savedAt: number;
  query: string;
  results: ChunkResult[];
  searchId: string | null;
  collections: string[];
  translation: string;
  quota: number;
  visibleCollections: string[];
  outcome: SearchOutcome | null;
  collectionOutcomes: Record<string, CollectionOutcome>;
}

export interface RestoredGuestSearch {
  readonly continuity: GuestContinuitySnapshot;
  readonly visibleCollections: readonly string[];
}

export function readGuestSearch(): RestoredGuestSearch | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(GUEST_RESULTS_KEY) ?? "null") as Partial<GuestResultsSnapshot> | null;
    if (!value || typeof value.savedAt !== "number"
      || Date.now() - value.savedAt > GUEST_RESULTS_MAX_AGE_MS) return null;
    if (typeof value.query !== "string" || !Array.isArray(value.results)
      || !Array.isArray(value.collections)) return null;
    if (typeof value.translation !== "string" || typeof value.quota !== "number"
      || !Array.isArray(value.visibleCollections)) return null;
    const snapshot = value as GuestResultsSnapshot;
    return {
      continuity: {
        savedAt: snapshot.savedAt,
        request: {
          query: snapshot.query,
          collections: snapshot.collections,
          translation: snapshot.translation,
          quota: snapshot.quota,
          origin: "fresh",
        },
        searchId: snapshot.searchId,
        passages: snapshot.results,
        outcome: snapshot.outcome,
        collectionOutcomes: snapshot.collectionOutcomes,
        visibleCollections: snapshot.visibleCollections,
      },
      visibleCollections: snapshot.visibleCollections,
    };
  } catch {
    return null;
  }
}

function clearGuestSearch() {
  try { sessionStorage.removeItem(GUEST_RESULTS_KEY); } catch {}
}

function saveGuestSearch(continuity: GuestContinuitySnapshot) {
  const snapshot: GuestResultsSnapshot = {
    savedAt: continuity.savedAt,
    query: continuity.request.query,
    results: [...continuity.passages],
    searchId: continuity.searchId,
    collections: [...continuity.request.collections],
    translation: continuity.request.translation,
    quota: continuity.request.quota,
    visibleCollections: [...(continuity.visibleCollections ?? continuity.request.collections)],
    outcome: continuity.outcome,
    collectionOutcomes: { ...continuity.collectionOutcomes },
  };
  try { sessionStorage.setItem(GUEST_RESULTS_KEY, JSON.stringify(snapshot)); } catch {}
}

function classifyError(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("rate limit") || lower.includes("429")) return "rate_limit";
  if (lower.includes("unauthorized") || lower.includes("401") || lower.includes("403")) return "auth_error";
  if (lower.includes("network") || lower.includes("fetch") || lower.includes("failed to fetch")) return "network_error";
  return "server_error";
}

class InvalidSavedSearchIdError extends Error {}

function classifySavedSearchFailure(error: unknown) {
  if (error instanceof InvalidSavedSearchIdError) {
    return {
      message: "This saved search link is invalid.",
      code: "restore_not_found",
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
      : classifyError(message),
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

interface SearchSummary {
  readonly id: string;
  readonly filters?: { readonly collections?: readonly string[] } | null;
}

interface GuestGate {
  readonly searchCount: number;
  readonly requestSignup: (reason: "limit") => void;
  readonly recordCompletedSearch: () => void;
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
  readonly setPendingSearch: (entryId: string, query: string) => void;
  readonly clearPendingSearch: () => void;
  readonly setActiveSearchId: (searchId: string | null) => void;
  readonly refreshSearches: () => void;
  readonly onFirstGuestSearchWithResults: () => void;
}

function createSearchPageExperience(options: SearchPageExperienceOptions) {
  let current = options;
  const experience = (() => {
    if (options.isGuest) {
      return createSearchExperience({
        audience: {
          kind: "guest",
          search: (request, callbacks, signal) => streamGuestSearch(
            getGuestSessionToken(),
            request.query,
            { collections: [...request.collections], translation: request.translation },
            request.quota,
            {
              onStatus: callbacks.onStatus,
              onChunk: callbacks.onPassage,
              onResultsReady: callbacks.onResultsReady,
              onExplanationDelta: callbacks.onExplanationDelta,
              onDone: callbacks.onDone,
              onError: callbacks.onError,
              onRateLimit: callbacks.onRateLimit,
            },
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
              current.onFirstGuestSearchWithResults();
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
          { collections: [...request.collections], translation: request.translation },
          request.quota,
          {
            onStatus: callbacks.onStatus,
            onChunk: callbacks.onPassage,
            onExplanationDelta: callbacks.onExplanationDelta,
            onDone: callbacks.onDone,
            onError: callbacks.onError,
            onRateLimit: callbacks.onRateLimit,
          },
          signal,
        ),
      },
      credentials: { current: () => current.token },
      savedSearch: {
        async restore(credential, searchId, signal) {
          const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
          if (!UUID_RE.test(searchId)) throw new InvalidSavedSearchIdError(searchId);
          const data = await getSearchResults(credential, searchId, signal);
          const responseCollections = data.filters?.collections;
          const storedCollections = Array.isArray(responseCollections)
            ? responseCollections
            : current.searches.find((search) => search.id === searchId)?.filters?.collections;
          const askedCollections = Array.isArray(storedCollections)
            ? storedCollections.filter((collection): collection is string =>
                typeof collection === "string" && ALL_COLLECTION_KEYS.includes(collection))
            : [];
          const collections = askedCollections.length > 0
            ? askedCollections
            : [...new Set(data.results.map((passage) => passage.source.collection))];
          const translation = typeof data.filters?.translation === "string" && data.filters.translation
            ? data.filters.translation
            : current.translation;
          const quota = typeof data.filters?.quota === "number" && [3, 4, 5].includes(data.filters.quota)
            ? data.filters.quota
            : current.quota;
          return {
            searchId: data.search_id,
            request: {
              query: data.query,
              collections,
              translation,
              quota,
              origin: "fresh" as const,
            },
            passages: data.results,
            warning: data.restore_status === "results_unavailable"
              ? `This saved search originally had ${data.expected_result_count} results, but only ${data.results.length} remain available.`
              : null,
          };
        },
        classifyFailure: classifySavedSearchFailure,
      },
      pendingHistory: {
        begin(entryId, query) {
          current.setPendingSearch(entryId, query);
          current.setActiveSearchId(entryId);
        },
        clear: () => current.clearPendingSearch(),
        activate: (searchId) => current.setActiveSearchId(searchId),
        refresh: () => current.refreshSearches(),
      },
      ids: { pendingEntry: () => crypto.randomUUID() },
      analytics: searchAnalytics,
    });
  })();

  return {
    experience,
    update(next: SearchPageExperienceOptions) { current = next; },
  };
}

export function useSearchPageExperience(options: SearchPageExperienceOptions) {
  const [lease] = useState(() => createSearchPageExperience(options));
  useLayoutEffect(() => { lease.update(options); }, [lease, options]);

  const snapshot = useSearchExperience(lease.experience);
  useLayoutEffect(() => {
    if (options.isGuest) return;
    lease.experience.send({ type: "identity-changed", userId: options.userId });
  }, [lease, options.isGuest, options.userId]);
  return { experience: lease.experience, snapshot };
}
