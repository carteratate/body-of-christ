"use client";

import { useLayoutEffect, useRef, useState } from "react";

import {
  getSearchResults,
  SearchRestoreHttpError,
  streamGuestSearch,
  streamSearch,
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
  Passage,
  SearchTransportCallbacks,
} from "./types";
import { useSearchExperience } from "./useSearchExperience";
import { searchExperienceView } from "./view";

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
        passages: passages as Passage[],
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
  try { sessionStorage.removeItem(GUEST_CONTINUITY_KEY); } catch {}
}

function saveGuestSearch(continuity: GuestContinuitySnapshot) {
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
  };
  try { sessionStorage.setItem(GUEST_CONTINUITY_KEY, JSON.stringify(snapshot)); } catch {}
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

function adaptTransportCallbacks(callbacks: SearchTransportCallbacks) {
  return {
    onStatus: callbacks.onStatus,
    onChunk: callbacks.onPassage,
    onResultsReady: callbacks.onResultsReady,
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
  readonly activate: (searchId: string | null) => void;
  readonly refresh: () => void;
}

interface SearchPageViewSynchronization {
  readonly setVisibleCollections: (collections: string[]) => void;
  readonly clearDraft: () => void;
  readonly deactivateHistory: () => void;
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
          { collections: [...request.collections], translation: request.translation },
          request.quota,
          adaptTransportCallbacks(callbacks),
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
              ? `This saved search originally had ${data.expected_result_count} Passages, but only ${data.results.length} remain available.`
              : null,
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
        activate(searchId) {
          current.pendingHistory.activate(searchId);
        },
        refresh: () => current.pendingHistory.refresh(),
      },
      ids: { pendingEntry: () => crypto.randomUUID() },
      analytics: searchAnalytics,
    });
  })();

  return {
    experience,
    read: () => current,
    update(next: SearchPageExperienceOptions) { current = next; },
  };
}

export function useSearchPageExperience(options: SearchPageExperienceOptions) {
  const [binding] = useState(() => createSearchPageExperience(options));
  useLayoutEffect(() => { binding.update(options); }, [binding, options]);

  const snapshot = useSearchExperience(binding.experience);
  const view = searchExperienceView(snapshot);
  useLayoutEffect(() => {
    if (options.isGuest) return;
    binding.experience.send({ type: "identity-changed", userId: options.userId });
  }, [binding, options.isGuest, options.userId]);

  const synchronizedRun = useRef<number | null>(
    options.isGuest && options.restoredGuestSearch ? snapshot.runId : null,
  );
  useLayoutEffect(() => {
    const synchronization = binding.read().viewSynchronization;
    if (view.active && synchronizedRun.current !== view.active.runId) {
      synchronizedRun.current = view.active.runId;
      synchronization.setVisibleCollections([...view.active.request.collections]);
      return;
    }
    if (options.isGuest) return;
    if (view.restored && synchronizedRun.current !== view.restored.runId) {
      synchronizedRun.current = view.restored.runId;
      synchronization.setVisibleCollections([...view.restored.request.collections]);
      return;
    }
    if (view.restoring || view.failure?.failure.kind === "restore") {
      synchronizedRun.current = snapshot.runId;
      synchronization.setVisibleCollections([]);
      synchronization.deactivateHistory();
      if (view.restoring) synchronization.clearDraft();
    }
  }, [binding, options.isGuest, snapshot.runId, view.active, view.failure?.failure.kind, view.restored, view.restoring]);

  return { experience: binding.experience, snapshot, view };
}
