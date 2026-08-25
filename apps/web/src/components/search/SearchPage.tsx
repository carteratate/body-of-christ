"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, Suspense } from "react";
import { Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { BottomBar } from "@/components/search/BottomBar";
import { EmptyState } from "@/components/search/EmptyState";
import { SearchResults } from "@/components/search/SearchResults";
import { LoadingAnimation } from "@/components/search/LoadingAnimation";
import { SearchFailureScreen } from "@/components/search/SearchFailureScreen";
import { RateLimitModal } from "@/components/common";
import { ALL_COLLECTION_KEYS } from "@/lib/collections";
import {
  streamSearch,
  streamGuestSearch,
  getSearchResults,
  SearchRestoreHttpError,
  updatePreferences,
  type ChunkResult,
  type CollectionOutcome,
  type SearchOutcome,
} from "@/lib/api";
import { getGuestSessionToken, GUEST_SEARCH_LIMIT } from "@/lib/trial";
import { useGuestGate } from "@/components/layout/guestGate";
import { saveFeedbackContext } from "@/lib/feedbackContext";
import {
  trackSearchPerformed,
  trackErrorOccurred,
  trackQuotaChanged,
} from "@/lib/analytics";
import {
  createSearchExperience,
  useSearchExperience,
  type ActiveSearchSnapshot,
  type AuthenticatedSearchExperiencePorts,
  type FailureSnapshot,
  type GuestContinuitySnapshot,
} from "@/lib/search-experience";
import { useAuthenticatedSearchRoute } from "@/lib/search-experience/useAuthenticatedSearchRoute";

function classifyError(msg: string): string {
  const lower = msg.toLowerCase();
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

function readGuestResultsSnapshot(): { continuity: GuestContinuitySnapshot; visibleCollections: string[] } | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(GUEST_RESULTS_KEY) ?? "null") as Partial<GuestResultsSnapshot> | null;
    if (!value || typeof value.savedAt !== "number" || Date.now() - value.savedAt > GUEST_RESULTS_MAX_AGE_MS) return null;
    if (typeof value.query !== "string" || !Array.isArray(value.results) || !Array.isArray(value.collections)) return null;
    if (typeof value.translation !== "string" || typeof value.quota !== "number" || !Array.isArray(value.visibleCollections)) return null;
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

function clearGuestResultsSnapshot() {
  try { sessionStorage.removeItem(GUEST_RESULTS_KEY); } catch {}
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

function SearchPageInner({ isGuest = false }: { isGuest?: boolean }) {
  const router = useRouter();
  const guestGate = useGuestGate();
  const {
    token, userId, preferences,
    searchKey,
    searches,
    setActiveSearchId,
    setPendingSearch, clearPendingSearch,
    refreshSearches,
  } = useAppContext();

  const tokenRef = useRef(token);
  useLayoutEffect(() => { tokenRef.current = token; }, [token]);

  // refreshSearches changes when token changes — keep current version in a ref
  // so the onDone closure always calls the up-to-date function.
  const refreshSearchesRef = useRef(refreshSearches);
  useEffect(() => { refreshSearchesRef.current = refreshSearches; });

  // History list, kept in a ref so the restore effect can recover a past
  // search's requested collections without re-running when the list refreshes.
  const searchesRef = useRef(searches);
  useEffect(() => { searchesRef.current = searches; });

  const searchParams = useSearchParams();
  const restoreId = searchParams.get("restore");
  const exploreQuery = searchParams.get("explore");
  const exploreRef = searchParams.get("exploreRef");
  const restoredGuestContinuity = useRef(isGuest ? readGuestResultsSnapshot() : null);

  // ── State ─────────────────────────────────────────────────────────────────

  const [activeCollections, setActiveCollections] = useState<string[]>(() => {
    if (isGuest) return ["bible", "catechism", "church-fathers", "summa", "councils", "encyclicals"];
    const cols = preferences?.default_collections;
    return cols && cols.length > 0 ? cols : [];
  });
  const [translation, setTranslation] = useState<string>(() =>
    preferences?.preferred_translation || "CPDV"
  );
  const [submittedTranslation] = useState<string>("");
  const [quota, setQuota] = useState<number>(() =>
    isGuest ? 3 : (preferences?.default_quota ?? 4)
  );
  const translationRef = useRef(translation);
  const quotaRef = useRef(quota);
  useLayoutEffect(() => {
    translationRef.current = translation;
    quotaRef.current = quota;
  }, [quota, translation]);
  const [searchValue, setSearchValue] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [results, setResults] = useState<ChunkResult[]>([]);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [queryBubbleVisible, setQueryBubbleVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [errorStage, setErrorStage] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<SearchOutcome | null>(null);
  const [collectionOutcomes, setCollectionOutcomes] = useState<Record<string, CollectionOutcome>>({});
  const [saveWarning, setSaveWarning] = useState<string | null>(null);
  const [rateLimitRetryAfter, setRateLimitRetryAfter] = useState<number | null>(null);
  const [rateLimitType] = useState<"per_minute" | "daily">("per_minute");
  const [searchPhase, setSearchPhase] = useState<"searching" | "ranking" | null>(null);
  const [exploreLabel, setExploreLabel] = useState<string | null>(null);
  const [showAnimation, setShowAnimation] = useState(false);
  const [animationRequestId] = useState(0);
  const [queryDone, setQueryDone] = useState(false);
  // Controls when BottomBar switches from search input → filter pills during animation.
  // Starts false (search input visible), then follows LoadingAnimation's filters-ready milestone.
  const [animFilterBarActive, setAnimFilterBarActive] = useState(false);
  const [submittedCollections, setSubmittedCollections] = useState<string[]>([]);
  const [submittedQuota] = useState<number | null>(null);
  const [visibleCollections, setVisibleCollections] = useState<string[]>(
    () => restoredGuestContinuity.current?.visibleCollections ?? [],
  );
  // Measured footprint of the query bubble shown during the animation — passed to
  // LoadingAnimation so its radial constellation shrinks to never overlap the bubble.
  const [bubbleSize, setBubbleSize] = useState<{ width: number; height: number } | null>(null);
  const [showFirstSearchHint, setShowFirstSearchHint] = useState(false);
  const [showFirstContextHint, setShowFirstContextHint] = useState(false);

  // ── Abort in-flight streams on unmount ───────────────────────────────────

  const activeRequestRef = useRef(0);
  const exploreTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prefsSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prefsMountedRef = useRef(false);
  const bufferedChunksRef = useRef<ChunkResult[]>([]);
  const bufferedExplRef   = useRef<Record<string, string>>({});
  // True once handleAnimReadyToShow has run — explanation deltas that arrive
  // after the animation resolves update results state directly (live streaming).
  const resolvedRef = useRef(false);
  const bubbleRef = useRef<HTMLDivElement>(null);

  // useLayoutEffect (not useEffect) so LoadingAnimation's first paint already
  // knows the bubble's footprint — avoids a visible resize/jump of the constellation.
  useLayoutEffect(() => {
    if (!showAnimation || !queryBubbleVisible || !submittedQuery || exploreLabel) {
      setBubbleSize(null);
      return;
    }
    const el = bubbleRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (width > 0 && height > 0) setBubbleSize({ width, height });
  }, [showAnimation, queryBubbleVisible, submittedQuery, exploreLabel]);

  useEffect(() => {
    return () => {
      activeRequestRef.current += 1;
      if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
      if (prefsSaveTimerRef.current) clearTimeout(prefsSaveTimerRef.current);
    };
  }, []);

  // ── Unified preferences save ──────────────────────────────────────────────
  // Single debounced effect for all three preference fields. Saves in one call
  // so rapid collection/quota/translation changes collapse to one API request.
  // Guard skips empty-collections state (avoids 422 when all are deselected).
  useEffect(() => {
    if (!prefsMountedRef.current) {
      prefsMountedRef.current = true;
      return;
    }
    if (!token || activeCollections.length === 0) return;
    if (prefsSaveTimerRef.current) clearTimeout(prefsSaveTimerRef.current);
    prefsSaveTimerRef.current = setTimeout(() => {
      updatePreferences(token, {
        default_collections: activeCollections,
        default_quota: quota,
        preferred_translation: translation,
      }).catch(() => {});
    }, 800);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCollections, quota, translation]); // token is stable for a session

  // ── Pending sidebar slot ──────────────────────────────────────────────────
  // Tracks the ID of the current "New Search" placeholder. null = no placeholder
  // (either a real search was submitted and completed, or we're in a restored view).

  const pendingIdRef = useRef<string | null>(null);
  const pendingPlaceholderRef = useRef<string | null>(null);

  const [authenticatedExperience] = useState(() => createSearchExperience({
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
    credentials: { current: () => tokenRef.current },
    savedSearch: {
      async restore(credential, searchId, signal) {
        const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        if (!UUID_RE.test(searchId)) throw new InvalidSavedSearchIdError(searchId);
        const data = await getSearchResults(credential, searchId, signal);
        const responseCollections = data.filters?.collections;
        const storedCollections = Array.isArray(responseCollections)
          ? responseCollections
          : searchesRef.current.find((search) => search.id === searchId)?.filters?.collections;
        const askedCollections = Array.isArray(storedCollections)
          ? storedCollections.filter((collection): collection is string =>
              typeof collection === "string" && ALL_COLLECTION_KEYS.includes(collection))
          : [];
        const collections = askedCollections.length > 0
          ? askedCollections
          : [...new Set(data.results.map((passage) => passage.source.collection))];
        const translation = typeof data.filters?.translation === "string" && data.filters.translation
          ? data.filters.translation
          : translationRef.current;
        const quota = typeof data.filters?.quota === "number" && [3, 4, 5].includes(data.filters.quota)
          ? data.filters.quota
          : quotaRef.current;
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
        pendingIdRef.current = entryId;
        setPendingSearch(entryId, query);
        setActiveSearchId(entryId);
      },
      clear(entryId) {
        if (pendingIdRef.current !== entryId) return;
        pendingIdRef.current = null;
        clearPendingSearch();
      },
      refresh: () => refreshSearchesRef.current(),
    },
    ids: {
      pendingEntry() {
        const placeholderId = pendingPlaceholderRef.current;
        pendingPlaceholderRef.current = null;
        return placeholderId ?? crypto.randomUUID();
      },
    },
    analytics: searchAnalytics,
  }));
  const authenticatedSnapshot = useSearchExperience(authenticatedExperience);
  useLayoutEffect(() => {
    if (isGuest) return;
    authenticatedExperience.send({ type: "identity-changed", userId });
  }, [authenticatedExperience, isGuest, userId]);
  const guestGateRef = useRef(guestGate);
  useEffect(() => { guestGateRef.current = guestGate; }, [guestGate]);
  const [guestExperience] = useState(() => createSearchExperience({
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
      canSearch: () => (guestGateRef.current?.searchCount ?? 0) < GUEST_SEARCH_LIMIT,
      requestSignup: (reason) => guestGateRef.current?.requestSignup(reason),
      recordCompletedSearch(resultCount) {
        const gate = guestGateRef.current;
        const completedNumber = (gate?.searchCount ?? 0) + 1;
        gate?.recordCompletedSearch();
        if (completedNumber === 1 && resultCount > 0) setShowFirstSearchHint(true);
      },
    },
    guestContinuity: {
      restore: () => restoredGuestContinuity.current?.continuity ?? null,
      save(continuity) {
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
      },
      clear: clearGuestResultsSnapshot,
    },
    time: { now: Date.now },
    analytics: searchAnalytics,
  }));
  const guestSnapshot = useSearchExperience(guestExperience);
  const replaceWithSearchRoute = useCallback(() => router.replace("/search"), [router]);
  const routeSearchDefaults = useMemo(() => ({
    collections: activeCollections,
    translation,
    quota,
  }), [activeCollections, quota, translation]);
  const authenticatedRoute = useAuthenticatedSearchRoute({
    experience: authenticatedExperience,
    snapshot: authenticatedSnapshot,
    restoreId,
    userId: isGuest ? null : userId,
    credential: isGuest ? null : token,
    exploreQuery,
    exploreReference: exploreRef,
    defaults: routeSearchDefaults,
    replaceWithSearchRoute,
  });

  function activatePendingSlot() {
    if (pendingIdRef.current) {
      // Reuse existing placeholder — prevents duplicates
      setActiveSearchId(pendingIdRef.current);
    } else {
      const id = crypto.randomUUID();
      pendingIdRef.current = id;
      pendingPlaceholderRef.current = id;
      setPendingSearch(id, "New Search");
      setActiveSearchId(id);
    }
  }

  // On initial mount: show placeholder unless we're restoring a past search.
  const mountRestoreId = useRef(restoreId);
  useEffect(() => {
    if (mountRestoreId.current) return;
    activatePendingSlot();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentional: runs once at mount only

  const activatedCompletedSearchRef = useRef<string | null>(null);
  useEffect(() => {
    if (isGuest) return;
    const completedSearchId = authenticatedSnapshot.status === "restored-results"
      ? authenticatedSnapshot.searchId
      : authenticatedSnapshot.status === "active-search"
        && authenticatedSnapshot.transport.status === "complete"
        ? authenticatedSnapshot.transport.searchId
        : null;
    if (!completedSearchId || activatedCompletedSearchRef.current === completedSearchId) return;
    activatedCompletedSearchRef.current = completedSearchId;
    setActiveSearchId(completedSearchId);
  }, [authenticatedSnapshot, isGuest, setActiveSearchId]);

  // ── Reset on New Search ───────────────────────────────────────────────────

  const prevSearchKey = useRef(searchKey);

  useEffect(() => {
    if (prevSearchKey.current === searchKey) return;
    prevSearchKey.current = searchKey;
    if (isGuest) guestExperience.send({ type: "reset" });
    else authenticatedExperience.send({ type: "reset" });
    activeRequestRef.current += 1;
    if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
    authenticatedRoute.cancelPendingExplore();
    setResults([]);
    setSubmittedQuery(null);
    setQueryBubbleVisible(false);
    setSearchId(null);
    setError(null);
    setErrorCode(null);
    setErrorStage(null);
    setOutcome(null);
    setCollectionOutcomes({});
    setSaveWarning(null);
    setLoading(false);
    setSearchValue("");
    setSearchPhase(null);
    setRateLimitRetryAfter(null);
    setExploreLabel(null);
    setSubmittedCollections([]);
    setVisibleCollections([]);
    setShowAnimation(false);
    setQueryDone(false);
    setAnimFilterBarActive(false);
    bufferedChunksRef.current = [];
    bufferedExplRef.current   = {};
    resolvedRef.current = false;
    activatePendingSlot();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchKey]); // activatePendingSlot is intentionally excluded (uses refs only)

  // ── Search ────────────────────────────────────────────────────────────────

  const handleSearch = useCallback(
    async (
      queryOverride?: string,
      newExploreLabel?: string,
      collectionsOverride?: string[],
      translationOverride?: string,
      quotaOverride?: number,
    ) => {
      const query = queryOverride ?? searchValue;
      const searchCollections = collectionsOverride ?? activeCollections;
      const searchTranslation = translationOverride ?? translation;
      const searchQuota = quotaOverride ?? quota;
      if (searchCollections.length === 0 || !query.trim()) return;
      if (isGuest) {
        setSearchValue("");
        setVisibleCollections([...searchCollections]);
        guestExperience.send({
          type: "submit",
          request: {
            query,
            collections: searchCollections,
            translation: searchTranslation,
            quota: searchQuota,
            origin: newExploreLabel ? "explore" : "fresh",
            ...(newExploreLabel ? { exploreLabel: newExploreLabel } : {}),
          },
        });
        return;
      }
      activeRequestRef.current += 1;
      activatedCompletedSearchRef.current = null;
      setSearchValue("");
      setVisibleCollections([...searchCollections]);
      authenticatedExperience.send({
        type: "submit",
        request: {
          query,
          collections: searchCollections,
          translation: searchTranslation,
          quota: searchQuota,
          origin: newExploreLabel ? "explore" : "fresh",
          ...(newExploreLabel ? { exploreLabel: newExploreLabel } : {}),
        },
      });
    },
    [activeCollections, translation, quota, searchValue, isGuest, authenticatedExperience, guestExperience]
  );

  // ── Animation ─────────────────────────────────────────────────────────────

  function handleAnimReadyToShow(requestId: number) {
    if (isGuest || authenticatedSnapshot.status === "active-search") {
      (isGuest ? guestExperience : authenticatedExperience).send({
        type: "animation",
        runId: requestId,
        milestone: "ready-to-reveal",
      });
      return;
    }
    if (activeRequestRef.current !== requestId) return;
    const merged = bufferedChunksRef.current.map(chunk => ({
      ...chunk,
      explanation: bufferedExplRef.current[chunk.chunk_id] ?? null,
    }));
    resolvedRef.current = true;  // subsequent explanation deltas go directly to results
    setResults(merged);
    setLoading(false);
    setQueryBubbleVisible(true);
    // showAnimation stays true so the overlay can fade out over the results
    setQueryDone(false);
  }

  function handleAnimFiltersReady(requestId: number) {
    if (isGuest || authenticatedSnapshot.status === "active-search") {
      (isGuest ? guestExperience : authenticatedExperience).send({
        type: "animation",
        runId: requestId,
        milestone: "filters-ready",
      });
      return;
    }
    if (activeRequestRef.current !== requestId) return;
    setAnimFilterBarActive(true);
  }

  function handleAnimFadeComplete(requestId: number) {
    if (isGuest || authenticatedSnapshot.status === "active-search") {
      (isGuest ? guestExperience : authenticatedExperience).send({
        type: "animation",
        runId: requestId,
        milestone: "fade-complete",
      });
      return;
    }
    if (activeRequestRef.current !== requestId) return;
    setShowAnimation(false);
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  function handleToggleCollection(c: string) {
    setActiveCollections((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
    );
  }

  function handleToggleVisible(c: string) {
    const next = visibleCollections.includes(c)
      ? visibleCollections.filter((value) => value !== c)
      : [...visibleCollections, c];
    setVisibleCollections(next);
    if (isGuest) {
      guestExperience.send({ type: "guest-visible-collections-changed", collections: next });
    }
  }

  function handleQuotaChange(q: number) {
    trackQuotaChanged({ from: quota, to: q });
    setQuota(q);
  }

  function handleSelectQuery(text: string) {
    setSearchValue(text);
    handleSearch(text);
  }

  const handleExploreMore = useCallback((content: string, label: string) => {
    if (!isGuest) {
      authenticatedRoute.queryMoreLike(content, label);
      return;
    }
    if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
    exploreTimerRef.current = setTimeout(() => {
      handleSearch(content, label);
    }, 300);
  }, [authenticatedRoute, handleSearch, isGuest]);

  const runtimeSnapshot = isGuest ? guestSnapshot : authenticatedSnapshot;
  const runtimeActive: ActiveSearchSnapshot | null = runtimeSnapshot.status === "active-search"
    ? runtimeSnapshot
    : null;
  const runtimeRestored = runtimeSnapshot.status === "restored-results"
    ? runtimeSnapshot
    : null;
  const runtimeRestoring = runtimeSnapshot.status === "restoring";
  const runtimeFailure: FailureSnapshot | null = runtimeSnapshot.status === "failure"
    ? runtimeSnapshot
    : null;
  const runtimeOwnsSearchView = runtimeSnapshot.status !== "idle";
  const runtimeRequest = runtimeActive?.request
    ?? runtimeRestored?.request
    ?? runtimeFailure?.request
    ?? null;
  const runtimeTransport = runtimeActive?.transport ?? null;
  const renderedLoading = runtimeOwnsSearchView
    ? runtimeRestoring || runtimeActive?.presentation.status === "animating"
    : loading;
  const renderedPassages = useMemo(
    () => runtimeOwnsSearchView
      ? [...(runtimeActive?.passages ?? runtimeRestored?.passages ?? [])]
      : results,
    [runtimeActive?.passages, runtimeRestored?.passages, results, runtimeOwnsSearchView],
  );
  const renderedSearchId = runtimeOwnsSearchView
    ? runtimeRestored?.searchId
      ?? (runtimeTransport?.status === "complete" ? runtimeTransport.searchId : null)
    : searchId;
  const renderedSubmittedQuery = runtimeOwnsSearchView ? runtimeRequest?.query ?? null : submittedQuery;
  const renderedQueryBubbleVisible = runtimeOwnsSearchView
    ? runtimeRestored !== null
      || (runtimeFailure?.request !== null && runtimeFailure?.request !== undefined)
      || (runtimeActive !== null && runtimeActive.presentation.status !== "animating")
    : queryBubbleVisible;
  const renderedError = runtimeOwnsSearchView ? runtimeFailure?.failure.message ?? null : error;
  const renderedErrorCode = runtimeOwnsSearchView ? runtimeFailure?.failure.code ?? null : errorCode;
  const renderedErrorStage = runtimeOwnsSearchView ? runtimeFailure?.failure.stage ?? null : errorStage;
  const renderedOutcome = runtimeOwnsSearchView
    ? runtimeRestored
      ? runtimeRestored.passages.length > 0 ? "success" : "no_candidates"
      : runtimeTransport?.status === "complete" ? runtimeTransport.outcome : null
    : outcome;
  const runtimeCompletionFailure = runtimeTransport?.status === "ranked-ready"
    ? runtimeTransport.completionFailure
    : null;
  const renderedCollectionOutcomes = runtimeOwnsSearchView
    ? runtimeFailure?.failure.collectionOutcomes
      ?? runtimeCompletionFailure?.collectionOutcomes
      ?? (runtimeTransport?.status === "complete" ? runtimeTransport.collectionOutcomes : {})
    : collectionOutcomes;
  const renderedSaveWarning = runtimeOwnsSearchView
    ? runtimeRestored?.warning ?? runtimeActive?.saveWarning ?? null
    : saveWarning;
  const renderedSearchPhase = runtimeOwnsSearchView
    ? runtimeTransport?.status === "searching" ? runtimeTransport.phase : null
    : searchPhase;
  const renderedExploreLabel = runtimeOwnsSearchView ? runtimeRequest?.exploreLabel ?? null : exploreLabel;
  const renderedShowAnimation = runtimeOwnsSearchView
    ? runtimeActive !== null && runtimeActive.presentation.status !== "revealed"
    : showAnimation;
  const renderedAnimationRequestId = runtimeOwnsSearchView
    ? runtimeSnapshot.runId
    : animationRequestId;
  const renderedQueryDone = runtimeOwnsSearchView
    ? runtimeActive?.presentation.status === "animating"
      && runtimeActive.presentation.resultsReady
    : queryDone;
  const renderedRetrievalStarted = runtimeOwnsSearchView
    ? runtimeTransport?.status !== "preparing"
    : searchPhase !== null || queryDone;
  const renderedFilterBarActive = runtimeOwnsSearchView
    ? runtimeActive?.presentation.filtersReady ?? false
    : animFilterBarActive;
  const renderedSubmittedCollections = runtimeOwnsSearchView
    ? [...(runtimeRequest?.collections ?? [])]
    : submittedCollections;
  const renderedSubmittedTranslation = runtimeOwnsSearchView
    ? runtimeRequest?.translation ?? ""
    : submittedTranslation;
  const renderedSubmittedQuota = runtimeOwnsSearchView
    ? runtimeRequest?.quota ?? null
    : submittedQuota;
  const renderedRateLimit = runtimeFailure?.failure.rateLimit?.open
    ? runtimeFailure.failure.rateLimit
    : runtimeCompletionFailure?.rateLimit?.open
      ? runtimeCompletionFailure.rateLimit
      : null;

  useLayoutEffect(() => {
    if (isGuest) return;
    if (runtimeRestored) {
      setVisibleCollections([...runtimeRestored.request.collections]);
      return;
    }
    if (runtimeRestoring || runtimeFailure?.failure.kind === "restore") {
      setVisibleCollections([]);
      setActiveSearchId(null);
      if (runtimeRestoring) setSearchValue("");
    }
  }, [isGuest, runtimeFailure?.failure.kind, runtimeRestored, runtimeRestoring, setActiveSearchId]);

  useLayoutEffect(() => {
    if (!runtimeOwnsSearchView) return;
    if (!renderedShowAnimation || !renderedQueryBubbleVisible
      || !renderedSubmittedQuery || renderedExploreLabel) {
      setBubbleSize(null);
      return;
    }
    const el = bubbleRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (width > 0 && height > 0) setBubbleSize({ width, height });
  }, [runtimeOwnsSearchView, renderedShowAnimation, renderedQueryBubbleVisible, renderedSubmittedQuery, renderedExploreLabel]);

  // Collections that actually have results — used for filter bar pills only.
  // Derived from results so it never shows buttons for collections that returned nothing.
  const filterBarCollections = useMemo(
    () => [...new Set(renderedPassages.map((passage) => passage.source.collection))],
    [renderedPassages]
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      <div className="relative flex-1 min-h-0 overflow-y-auto px-4 pt-4 pb-2">
        {/* Animation overlay — scoped to content area only, BottomBar stays visible */}
        {renderedShowAnimation && (
          <LoadingAnimation
            key={renderedAnimationRequestId}
            collections={renderedSubmittedCollections.length > 0 ? renderedSubmittedCollections : activeCollections}
            quota={renderedSubmittedQuota ?? quota}
            isQueryDone={renderedQueryDone}
            retrievalStarted={renderedRetrievalStarted}
            onFiltersReady={() => handleAnimFiltersReady(renderedAnimationRequestId)}
            onReadyToShow={() => handleAnimReadyToShow(renderedAnimationRequestId)}
            onFadeComplete={() => handleAnimFadeComplete(renderedAnimationRequestId)}
            reservedTopRight={bubbleSize}
          />
        )}

        {!renderedSubmittedQuery && !renderedLoading && !renderedError && (
          <EmptyState onSelectQuery={handleSelectQuery} />
        )}

        {/* Keep the revealed query in normal flow so results reserve its height.
            During the animation fade, z-20 places it above the z-10 overlay. */}
        {renderedQueryBubbleVisible && renderedSubmittedQuery && !renderedExploreLabel && (
          <div
            ref={bubbleRef}
            className={`relative flex justify-end mb-4 ${renderedShowAnimation ? "z-20 pointer-events-none" : ""}`}
          >
            <div className="max-w-[70%] max-md:max-w-[85%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
              {renderedSubmittedQuery}
            </div>
          </div>
        )}

        {renderedExploreLabel && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-brand-accent/10 border border-brand-accent/20">
            <Search size={14} className="text-brand-accent shrink-0" />
            <span className="text-sm text-brand-muted">
              Exploring passages related to{" "}
              <span className="text-brand-primary font-medium">{renderedExploreLabel}</span>
            </span>
          </div>
        )}

        {!renderedError && (renderedLoading || renderedSubmittedQuery) && (
          <SearchResults
            results={renderedPassages}
            loading={renderedLoading}
            searchId={renderedSearchId}
            token={token ?? ""}
            onExploreMore={handleExploreMore}
            phase={renderedSearchPhase}
            submittedCollections={renderedSubmittedCollections}
            visibleCollections={visibleCollections}
            outcome={renderedOutcome}
            collectionOutcomes={{ ...renderedCollectionOutcomes }}
            isRestoring={runtimeRestoring}
            isGuest={isGuest}
            showFirstSearchHint={showFirstSearchHint}
            onDismissFirstSearchHint={() => setShowFirstSearchHint(false)}
            showFirstContextHint={showFirstContextHint}
            onFirstResultExpanded={() => {
              if (!showFirstSearchHint) return;
              setShowFirstSearchHint(false);
              setShowFirstContextHint(true);
            }}
            onDismissFirstContextHint={() => setShowFirstContextHint(false)}
          />
        )}

        {renderedSaveWarning && !renderedLoading && !renderedError && (
          <div className="mt-3 rounded-lg border border-brand-accent/30 bg-brand-accent/10 px-4 py-3 text-sm text-brand-muted">
            {renderedSaveWarning}
          </div>
        )}

        {runtimeCompletionFailure && !runtimeCompletionFailure.rateLimit && !renderedLoading && (
          <div
            role="status"
            className="mt-3 rounded-lg border border-brand-accent/30 bg-brand-accent/10 px-4 py-3 text-sm text-brand-muted"
          >
            {runtimeCompletionFailure.message}
          </div>
        )}

        {renderedError && !renderedLoading && (
          <SearchFailureScreen
            message={renderedError}
            code={renderedErrorCode}
            stage={renderedErrorStage}
            onRetry={() => {
              if (runtimeFailure) {
                (isGuest ? guestExperience : authenticatedExperience).send({ type: "retry" });
                return;
              }
              if (renderedSubmittedQuery) void handleSearch(
                renderedSubmittedQuery,
                renderedExploreLabel ?? undefined,
                renderedSubmittedCollections,
                renderedSubmittedTranslation || translation,
                renderedSubmittedQuota ?? quota,
              );
            }}
            onReport={isGuest ? undefined : () => {
              const safeCode = (["auth_error", "network_error", "rate_limit", "restore_not_found", "restore_unavailable", "server_error", "stream_interrupted"] as const)
                .find((value) => value === renderedErrorCode) ?? "unknown";
              saveFeedbackContext({ category: "bug", origin: "search_error", route: "/search", search_id: renderedSearchId ?? undefined, error_code: safeCode });
              router.push("/feedback");
            }}
          />
        )}

      </div>

      <BottomBar
        activeCollections={renderedLoading && renderedSubmittedCollections.length > 0 ? renderedSubmittedCollections : activeCollections}
        onToggleCollection={handleToggleCollection}
        translation={renderedLoading && renderedSubmittedTranslation ? renderedSubmittedTranslation : translation}
        onTranslationChange={setTranslation}
        quota={renderedLoading && renderedSubmittedQuota !== null ? renderedSubmittedQuota : quota}
        onQuotaChange={handleQuotaChange}
        searchValue={searchValue}
        onSearchChange={(val) => {
          if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
          authenticatedRoute.cancelPendingExplore();
          setSearchValue(val);
        }}
        onSearch={() => handleSearch(searchValue)}
        loading={renderedLoading}
        isSearchActive={renderedShowAnimation ? renderedFilterBarActive : renderedSubmittedQuery !== null}
        submittedCollections={renderedShowAnimation ? renderedSubmittedCollections : filterBarCollections}
        visibleCollections={visibleCollections}
        onToggleVisible={handleToggleVisible}
        searchDisabled={false}
        fixedQuota={isGuest}
      />
      {(renderedRateLimit || rateLimitRetryAfter !== null) && (
        <RateLimitModal
          limitType={renderedRateLimit?.type ?? rateLimitType}
          retryAfter={renderedRateLimit?.retryAfter ?? rateLimitRetryAfter}
          onDismiss={() => {
            if (renderedRateLimit) {
              (isGuest ? guestExperience : authenticatedExperience).send({ type: "dismiss-rate-limit" });
            }
            else setRateLimitRetryAfter(null);
          }}
        />
      )}
    </div>
  );
}

export function SearchPage({ isGuest = false }: { isGuest?: boolean }) {
  return (
    <Suspense>
      <SearchPageInner isGuest={isGuest} />
    </Suspense>
  );
}
