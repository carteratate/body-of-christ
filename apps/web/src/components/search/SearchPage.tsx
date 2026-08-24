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

function classifyError(msg: string): string {
  const lower = msg.toLowerCase();
  if (lower.includes("rate limit") || lower.includes("429")) return "rate_limit";
  if (lower.includes("unauthorized") || lower.includes("401") || lower.includes("403")) return "auth_error";
  if (lower.includes("network") || lower.includes("fetch") || lower.includes("failed to fetch")) return "network_error";
  return "server_error";
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

function readGuestResultsSnapshot(): GuestResultsSnapshot | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(GUEST_RESULTS_KEY) ?? "null") as Partial<GuestResultsSnapshot> | null;
    if (!value || typeof value.savedAt !== "number" || Date.now() - value.savedAt > GUEST_RESULTS_MAX_AGE_MS) return null;
    if (typeof value.query !== "string" || !Array.isArray(value.results) || !Array.isArray(value.collections)) return null;
    if (typeof value.translation !== "string" || typeof value.quota !== "number" || !Array.isArray(value.visibleCollections)) return null;
    return value as GuestResultsSnapshot;
  } catch {
    return null;
  }
}

function clearGuestResultsSnapshot() {
  try { sessionStorage.removeItem(GUEST_RESULTS_KEY); } catch {}
}

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
  useEffect(() => { tokenRef.current = token; });

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
  const restoreScope = restoreId && userId ? `${userId}:${restoreId}` : null;
  const exploreQuery = searchParams.get("explore");
  const exploreRef = searchParams.get("exploreRef");

  // ── State ─────────────────────────────────────────────────────────────────

  const [activeCollections, setActiveCollections] = useState<string[]>(() => {
    if (isGuest) return ["bible", "catechism", "church-fathers", "summa", "councils", "encyclicals"];
    const cols = preferences?.default_collections;
    return cols && cols.length > 0 ? cols : [];
  });
  const [translation, setTranslation] = useState<string>(() =>
    preferences?.preferred_translation || "CPDV"
  );
  const [submittedTranslation, setSubmittedTranslation] = useState<string>("");
  const [quota, setQuota] = useState<number>(() =>
    isGuest ? 3 : (preferences?.default_quota ?? 4)
  );
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
  const [rateLimitType, setRateLimitType] = useState<"per_minute" | "daily">("per_minute");
  const [searchPhase, setSearchPhase] = useState<"searching" | "ranking" | null>(null);
  const [exploreLabel, setExploreLabel] = useState<string | null>(null);
  const [showAnimation, setShowAnimation] = useState(false);
  const [animationRequestId, setAnimationRequestId] = useState(0);
  const [queryDone, setQueryDone] = useState(false);
  // Controls when BottomBar switches from search input → filter pills during animation.
  // Starts false (search input visible), then follows LoadingAnimation's filters-ready milestone.
  const [animFilterBarActive, setAnimFilterBarActive] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [submittedCollections, setSubmittedCollections] = useState<string[]>([]);
  const [submittedQuota, setSubmittedQuota] = useState<number | null>(null);
  const [visibleCollections, setVisibleCollections] = useState<string[]>([]);
  // Measured footprint of the query bubble shown during the animation — passed to
  // LoadingAnimation so its radial constellation shrinks to never overlap the bubble.
  const [bubbleSize, setBubbleSize] = useState<{ width: number; height: number } | null>(null);
  const [showFirstSearchHint, setShowFirstSearchHint] = useState(false);
  const [showFirstContextHint, setShowFirstContextHint] = useState(false);
  const [queuedRestoreExplore, setQueuedRestoreExplore] = useState<{
    content: string;
    label: string;
    collections: string[];
    translation: string;
    quota: number;
  } | null>(null);

  // ── Abort in-flight streams on unmount ───────────────────────────────────

  const abortRef = useRef<AbortController | null>(null);
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

  // The guest search page unmounts while Reader is open. Keep the currently
  // displayed result set in same-tab storage so returning from context restores
  // the exact query instead of presenting a blank search screen.
  useLayoutEffect(() => {
    if (!isGuest) return;
    const snapshot = readGuestResultsSnapshot();
    if (!snapshot) return;
    setResults(snapshot.results);
    setSearchId(snapshot.searchId);
    setSubmittedQuery(snapshot.query);
    setQueryBubbleVisible(true);
    setSubmittedCollections(snapshot.collections);
    setSubmittedTranslation(snapshot.translation);
    setSubmittedQuota(snapshot.quota);
    setVisibleCollections(snapshot.visibleCollections);
    setOutcome(snapshot.outcome);
    setCollectionOutcomes(snapshot.collectionOutcomes);
    resolvedRef.current = true;
  }, [isGuest]);

  useEffect(() => {
    if (!isGuest || !submittedQuery || results.length === 0 || loading) return;
    const snapshot: GuestResultsSnapshot = {
      savedAt: Date.now(),
      query: submittedQuery,
      results,
      searchId,
      collections: submittedCollections,
      translation: submittedTranslation || translation,
      quota: submittedQuota ?? quota,
      visibleCollections,
      outcome,
      collectionOutcomes,
    };
    try { sessionStorage.setItem(GUEST_RESULTS_KEY, JSON.stringify(snapshot)); } catch {}
  }, [isGuest, submittedQuery, results, loading, searchId, submittedCollections, submittedTranslation, translation, submittedQuota, quota, visibleCollections, outcome, collectionOutcomes]);

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
      abortRef.current?.abort();
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

  function activatePendingSlot() {
    if (pendingIdRef.current) {
      // Reuse existing placeholder — prevents duplicates
      setActiveSearchId(pendingIdRef.current);
    } else {
      const id = crypto.randomUUID();
      pendingIdRef.current = id;
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

  // ── Reset on New Search ───────────────────────────────────────────────────

  const prevSearchKey = useRef(searchKey);
  const restoredForId = useRef<string | null>(null);
  const previousRestoreParam = useRef(restoreId);
  const exploredForQuery = useRef<string | null>(null);

  const resetRestorePresentation = useCallback(() => {
    pendingIdRef.current = null;
    clearPendingSearch();
    setActiveSearchId(null);
    setResults([]);
    setSubmittedQuery(null);
    setQueryBubbleVisible(false);
    setSearchValue("");
    setSearchId(null);
    setOutcome(null);
    setCollectionOutcomes({});
    setSubmittedCollections([]);
    setSubmittedTranslation("");
    setSubmittedQuota(null);
    setVisibleCollections([]);
    setError(null);
    setErrorCode(null);
    setErrorStage(null);
    setSaveWarning(null);
    setSearchPhase(null);
    setRateLimitRetryAfter(null);
    setExploreLabel(null);
    setShowAnimation(false);
    setQueryDone(false);
    setAnimFilterBarActive(false);
    if (exploreTimerRef.current) {
      clearTimeout(exploreTimerRef.current);
      exploreTimerRef.current = null;
    }
    bufferedChunksRef.current = [];
    bufferedExplRef.current = {};
    resolvedRef.current = false;
    exploredForQuery.current = null;
  }, [clearPendingSearch, setActiveSearchId]);

  useEffect(() => {
    if (prevSearchKey.current === searchKey) return;
    prevSearchKey.current = searchKey;
    if (isGuest) clearGuestResultsSnapshot();
    abortRef.current?.abort();
    activeRequestRef.current += 1;
    if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
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
    setIsRestoring(false);
    setSubmittedCollections([]);
    setVisibleCollections([]);
    setShowAnimation(false);
    setQueryDone(false);
    setAnimFilterBarActive(false);
    bufferedChunksRef.current = [];
    bufferedExplRef.current   = {};
    resolvedRef.current = false;
    restoredForId.current = null;
    exploredForQuery.current = null;
    activatePendingSlot();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchKey]); // activatePendingSlot is intentionally excluded (uses refs only)

  // ── Restore flow ──────────────────────────────────────────────────────────

  // useLayoutEffect (not useEffect): when switching to another past search, the
  // results are cleared below before the browser paints, so the loading
  // placeholders appear on the same frame as the click — no stale-results flash.
  useLayoutEffect(() => {
    const priorRestoreId = previousRestoreParam.current;
    previousRestoreParam.current = restoreId;
    if (!restoreId) {
      if (priorRestoreId) {
        abortRef.current?.abort();
        activeRequestRef.current += 1;
        restoredForId.current = null;
        resetRestorePresentation();
        setLoading(false);
        setIsRestoring(false);
      }
      return;
    }
    const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!UUID_RE.test(restoreId)) {
      abortRef.current?.abort();
      activeRequestRef.current += 1;
      resetRestorePresentation();
      setLoading(false);
      setIsRestoring(false);
      setError("This saved search link is invalid.");
      setErrorCode("restore_not_found");
      setErrorStage("restore");
      return;
    }
    if (!token || !userId || !restoreScope) {
      restoredForId.current = null;
      resetRestorePresentation();
      setLoading(false);
      setIsRestoring(false);
      return;
    }
    if (restoredForId.current === restoreScope) return;
    resetRestorePresentation();

    // Entering an old conversation — remove the "New Search" placeholder
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = activeRequestRef.current + 1;
    activeRequestRef.current = requestId;
    const isCurrentRequest = () => activeRequestRef.current === requestId;
    const id = restoreId;
    const tok = token;
    let requestFinished = false;
    restoredForId.current = restoreScope;
    setLoading(true);
    setIsRestoring(true);
    getSearchResults(tok, id, controller.signal)
      .then((data) => {
        if (!isCurrentRequest()) return;
        setResults(data.results);
        setSearchId(data.search_id);
        setSubmittedQuery(data.query);
        setQueryBubbleVisible(true);
        setSearchValue(data.query);
        setActiveSearchId(id);
        // Restore the collections this search actually requested, so the
        // "no passages met the threshold" notices only appear for sources that
        // were asked for. Prefer the stored filters from history; if unavailable
        // (e.g. deep-linked before history loaded), fall back to the collections
        // present in the results — which yields no spurious notices.
        const responseCollections = data.filters?.collections;
        const storedCollections = Array.isArray(responseCollections)
          ? responseCollections
          : searchesRef.current.find((s) => s.id === id)?.filters?.collections;
        const asked = Array.isArray(storedCollections)
          ? storedCollections.filter((c): c is string => typeof c === "string" && ALL_COLLECTION_KEYS.includes(c))
          : [];
        const restored = asked.length > 0
          ? asked
          : [...new Set(data.results.map((r) => r.source.collection))];
        setSubmittedCollections(restored);
        setSubmittedTranslation(
          typeof data.filters?.translation === "string" && data.filters.translation
            ? data.filters.translation
            : translation,
        );
        setSubmittedQuota(
          typeof data.filters?.quota === "number" && [3, 4, 5].includes(data.filters.quota)
            ? data.filters.quota
            : quota,
        );
        setVisibleCollections(restored);
        if (data.restore_status === "results_unavailable") {
          setError(
            `This saved search originally had ${data.expected_result_count} results, but only ${data.results.length} remain available.`
          );
          setErrorCode("restore_unavailable");
          setErrorStage("restore");
        } else {
          setOutcome(data.results.length > 0 ? "success" : "no_candidates");
        }
      })
      .catch((err: unknown) => {
        if (!isCurrentRequest() || (err as DOMException).name === "AbortError") return;
        const msg = err instanceof Error ? err.message : "Failed to restore search";
        restoredForId.current = null;
        setError(msg);
        if (err instanceof SearchRestoreHttpError && (err.status === 401 || err.status === 403)) {
          setErrorCode("auth_error");
          setErrorStage("authentication");
        } else {
          setErrorCode(
            err instanceof SearchRestoreHttpError && err.status === 404
              ? "restore_not_found"
              : (err as Error).name === "TimeoutError"
                ? "network_error"
                : "server_error"
          );
          setErrorStage("restore");
        }
      })
      .finally(() => {
        requestFinished = true;
        if (!isCurrentRequest()) return;
        setLoading(false);
        setIsRestoring(false);
      });
    return () => {
      if (activeRequestRef.current === requestId && !requestFinished) {
        // React Strict Mode replays layout effects in development, and the auth
        // token can also rotate while a restore is in flight. Let the replayed
        // effect start the same restore again instead of leaving the page on an
        // orphaned loading state after this request is invalidated.
        restoredForId.current = null;
        activeRequestRef.current += 1;
      }
      controller.abort();
    };
  }, [restoreId, restoreScope, token, userId, restoreAttempt, resetRestorePresentation, setActiveSearchId, translation, quota]);

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
      if (loading || searchCollections.length === 0 || !query.trim()) return;
      if (isGuest && (guestGate?.searchCount ?? 0) >= GUEST_SEARCH_LIMIT) {
        guestGate?.requestSignup("limit");
        return;
      }
      const currentToken = tokenRef.current;
      if (!isGuest && !currentToken) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const requestId = activeRequestRef.current + 1;
      activeRequestRef.current = requestId;
      setAnimationRequestId(requestId);
      let terminalReceived = false;
      let guestCompletionRecorded = false;
      const isCurrentRequest = () => activeRequestRef.current === requestId;

      // Update the pending slot title from "New Search" → actual query
      const pid = pendingIdRef.current ?? crypto.randomUUID();
      pendingIdRef.current = pid;
      setPendingSearch(pid, query);
      setActiveSearchId(pid);

      bufferedChunksRef.current = [];
      bufferedExplRef.current   = {};
      resolvedRef.current = false;
      setAnimFilterBarActive(false);
      setLoading(true);
      setSearchPhase(null);
      setError(null);
      setErrorCode(null);
      setErrorStage(null);
      setSearchId(null);
      setOutcome(null);
      setCollectionOutcomes({});
      setSaveWarning(null);
      setRateLimitRetryAfter(null);
      setRateLimitType("per_minute");
      setSubmittedQuery(query);
      setQueryBubbleVisible(false);
      setSearchValue("");
      setResults([]);
      setShowAnimation(true);
      setQueryDone(false);
      setExploreLabel(newExploreLabel ?? null);
      const snapshot = [...searchCollections];
      setSubmittedCollections(snapshot);
      setSubmittedTranslation(searchTranslation);
      setSubmittedQuota(searchQuota);
      setVisibleCollections(snapshot);
      if (isGuest) clearGuestResultsSnapshot();

      try {
        const streamCallbacks = {
          onStatus(phase: "searching" | "ranking") {
            if (!isCurrentRequest() || terminalReceived) return;
            setSearchPhase(phase);
          },
          onChunk(chunk: ChunkResult) {
            if (!isCurrentRequest() || terminalReceived) return;
            bufferedChunksRef.current.push({ ...chunk, explanation: null });
          },
          onResultsReady(resultCount: number) {
            if (!isGuest || !isCurrentRequest() || terminalReceived) return;
            // Reveal ranked cards immediately while explanation persistence and
            // transfer readiness continue in the server-owned producer.
            setQueryDone(true);
            if (!guestCompletionRecorded) {
              guestCompletionRecorded = true;
              const completedNumber = (guestGate?.searchCount ?? 0) + 1;
              guestGate?.recordCompletedSearch();
              if (completedNumber === 1 && resultCount > 0) setShowFirstSearchHint(true);
            }
          },
          onExplanationDelta(chunkId: string, delta: string) {
            if (!isCurrentRequest()) return;
            if (resolvedRef.current) {
              setResults(prev => prev.map(r =>
                r.chunk_id === chunkId
                  ? { ...r, explanation: (r.explanation ?? "") + delta }
                  : r
              ));
            } else {
              bufferedExplRef.current[chunkId] = (bufferedExplRef.current[chunkId] ?? "") + delta;
            }
          },
          onDone(
            sid: string | null,
            resultCount: number,
            searchOutcome: SearchOutcome,
            perCollection: Record<string, CollectionOutcome>,
            persisted: boolean,
          ) {
            if (!isCurrentRequest() || terminalReceived) return;
            terminalReceived = true;
            setSearchPhase(null);
            setSearchId(sid);
            setOutcome(searchOutcome);
            setCollectionOutcomes(perCollection);
            setSaveWarning(
              !isGuest && !persisted
                ? "Results are available now, but search history could not be saved. They will not be restorable after you leave this page."
                : null
            );
            setQueryDone(true);
            pendingIdRef.current = null;
            clearPendingSearch();
            if (sid && !isGuest) {
              setActiveSearchId(sid);
              refreshSearchesRef.current();
            }
            if (isGuest) {
              if (!guestCompletionRecorded) {
                guestCompletionRecorded = true;
                const completedNumber = (guestGate?.searchCount ?? 0) + 1;
                guestGate?.recordCompletedSearch();
                if (completedNumber === 1 && resultCount > 0) setShowFirstSearchHint(true);
              }
            }
            trackSearchPerformed({
              queryLength: query.length,
              collectionsUsed: snapshot,
              quotaPerSource: searchQuota,
              resultCount,
              translation: searchTranslation,
            });
          },
          onError(
            msg: string,
            code?: string,
            stage?: string,
            perCollection?: Record<string, CollectionOutcome>,
          ) {
            if (!isCurrentRequest() || terminalReceived) return;
            terminalReceived = true;
            if (isGuest && msg === "trial_exhausted") {
              setSearchPhase(null);
              setLoading(false);
              setShowAnimation(false);
              setAnimFilterBarActive(false);
              guestGate?.requestSignup("limit");
              return;
            }
            setSearchPhase(null);
            setError(msg);
            setErrorCode(code ?? classifyError(msg));
            setErrorStage(stage ?? null);
            setCollectionOutcomes(perCollection ?? {});
            setLoading(false);
            setShowAnimation(false);
            setAnimFilterBarActive(false);
            setQueryBubbleVisible(true);
            trackErrorOccurred({ page: "search", errorType: classifyError(msg) });
          },
          onRateLimit(retryAfter: number | null, limitType: "per_minute" | "daily") {
            if (!isCurrentRequest() || terminalReceived) return;
            terminalReceived = true;
            setSearchPhase(null);
            setRateLimitRetryAfter(retryAfter ?? 60);
            setRateLimitType(limitType);
            setLoading(false);
            setShowAnimation(false);
            setAnimFilterBarActive(false);
            setQueryBubbleVisible(true);
            setError(
              limitType === "daily"
                ? "You have reached today’s search limit."
                : "Too many searches were submitted in a short period."
            );
            setErrorCode("rate_limit");
            setErrorStage("rate_limit");
          },
        };

        if (isGuest) {
          await streamGuestSearch(
            getGuestSessionToken(),
            query,
            { collections: snapshot, translation: searchTranslation },
            searchQuota,
            streamCallbacks,
            controller.signal,
          );
        } else {
          await streamSearch(
            currentToken!,
            query,
            { collections: snapshot, translation: searchTranslation },
            searchQuota,
            streamCallbacks,
            controller.signal,
          );
        }
      } catch (err: unknown) {
        if (!isCurrentRequest() || terminalReceived) return;
        terminalReceived = true;
        const msg = err instanceof Error ? err.message : "Search failed";
        setError(msg);
        setErrorCode(classifyError(msg));
        setErrorStage("connection");
        setLoading(false);
        setShowAnimation(false);
        setAnimFilterBarActive(false);
        setQueryBubbleVisible(true);
        trackErrorOccurred({ page: "search", errorType: classifyError(msg) });
      }
    },
    [loading, activeCollections, translation, quota, searchValue, isGuest, guestGate, setPendingSearch, setActiveSearchId, clearPendingSearch]
  );

  // ── Animation ─────────────────────────────────────────────────────────────

  function handleAnimReadyToShow(requestId: number) {
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
    if (activeRequestRef.current !== requestId) return;
    setAnimFilterBarActive(true);
  }

  function handleAnimFadeComplete(requestId: number) {
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
    setVisibleCollections((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
    );
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
    if (restoreId) {
      setQueuedRestoreExplore({
        content,
        label,
        collections: submittedCollections,
        translation: submittedTranslation || translation,
        quota: submittedQuota ?? quota,
      });
      router.replace("/search");
      return;
    }
    if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
    exploreTimerRef.current = setTimeout(() => {
      handleSearch(content, label);
    }, 300);
  }, [handleSearch, quota, restoreId, router, submittedCollections, submittedQuota, submittedTranslation, translation]);

  useEffect(() => {
    if (!queuedRestoreExplore || restoreId) return;
    const request = queuedRestoreExplore;
    setQueuedRestoreExplore(null);
    void handleSearch(request.content, request.label, request.collections, request.translation, request.quota);
  }, [handleSearch, queuedRestoreExplore, restoreId]);

  // ── Explore flow (from ?explore= query param) ──────────────────────────────

  useEffect(() => {
    if (!exploreQuery || !token) return;
    if (exploredForQuery.current === exploreQuery) return;
    exploredForQuery.current = exploreQuery;
    const label = exploreRef?.trim()
      || (exploreQuery.slice(0, 60).replace(/\s+\S*$/, "") + (exploreQuery.length > 60 ? "…" : ""));
    void handleSearch(exploreQuery, label);
    router.replace("/search");
  }, [exploreQuery, exploreRef, token, handleSearch, router]);

  // Collections that actually have results — used for filter bar pills only.
  // Derived from results so it never shows buttons for collections that returned nothing.
  const filterBarCollections = useMemo(
    () => [...new Set(results.map((r) => r.source.collection))],
    [results]
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      <div className="relative flex-1 min-h-0 overflow-y-auto px-4 pt-4 pb-2">
        {/* Animation overlay — scoped to content area only, BottomBar stays visible */}
        {showAnimation && (
          <LoadingAnimation
            key={animationRequestId}
            collections={submittedCollections.length > 0 ? submittedCollections : activeCollections}
            quota={submittedQuota ?? quota}
            isQueryDone={queryDone}
            retrievalStarted={searchPhase !== null || queryDone}
            onFiltersReady={() => handleAnimFiltersReady(animationRequestId)}
            onReadyToShow={() => handleAnimReadyToShow(animationRequestId)}
            onFadeComplete={() => handleAnimFadeComplete(animationRequestId)}
            reservedTopRight={bubbleSize}
          />
        )}

        {!submittedQuery && !loading && !error && (
          <EmptyState onSelectQuery={handleSelectQuery} />
        )}

        {/* Keep the revealed query in normal flow so results reserve its height.
            During the animation fade, z-20 places it above the z-10 overlay. */}
        {queryBubbleVisible && submittedQuery && !exploreLabel && (
          <div
            ref={bubbleRef}
            className={`relative flex justify-end mb-4 ${showAnimation ? "z-20 pointer-events-none" : ""}`}
          >
            <div className="max-w-[70%] max-md:max-w-[85%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
              {submittedQuery}
            </div>
          </div>
        )}

        {exploreLabel && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-brand-accent/10 border border-brand-accent/20">
            <Search size={14} className="text-brand-accent shrink-0" />
            <span className="text-sm text-brand-muted">
              Exploring passages related to{" "}
              <span className="text-brand-primary font-medium">{exploreLabel}</span>
            </span>
          </div>
        )}

        {!error && (loading || submittedQuery) && (
          <SearchResults
            results={results}
            loading={loading}
            searchId={searchId}
            token={token ?? ""}
            onExploreMore={handleExploreMore}
            phase={searchPhase}
            submittedCollections={submittedCollections}
            visibleCollections={visibleCollections}
            outcome={outcome}
            collectionOutcomes={collectionOutcomes}
            isRestoring={isRestoring}
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

        {saveWarning && !loading && !error && (
          <div className="mt-3 rounded-lg border border-brand-accent/30 bg-brand-accent/10 px-4 py-3 text-sm text-brand-muted">
            {saveWarning}
          </div>
        )}

        {error && !loading && (
          <SearchFailureScreen
            message={error}
            code={errorCode}
            stage={errorStage}
            onRetry={() => {
              if (errorStage === "restore" && restoreId) {
                restoredForId.current = null;
                setRestoreAttempt((attempt) => attempt + 1);
                return;
              }
              if (submittedQuery) void handleSearch(
                submittedQuery,
                exploreLabel ?? undefined,
                submittedCollections,
                submittedTranslation || translation,
                submittedQuota ?? quota,
              );
            }}
            onReport={isGuest ? undefined : () => {
              const safeCode = (["auth_error", "network_error", "rate_limit", "restore_not_found", "restore_unavailable", "server_error", "stream_interrupted"] as const)
                .find((value) => value === errorCode) ?? "unknown";
              saveFeedbackContext({ category: "bug", origin: "search_error", route: "/search", search_id: searchId ?? undefined, error_code: safeCode });
              router.push("/feedback");
            }}
          />
        )}

      </div>

      <BottomBar
        activeCollections={loading && submittedCollections.length > 0 ? submittedCollections : activeCollections}
        onToggleCollection={handleToggleCollection}
        translation={loading && submittedTranslation ? submittedTranslation : translation}
        onTranslationChange={setTranslation}
        quota={loading && submittedQuota !== null ? submittedQuota : quota}
        onQuotaChange={handleQuotaChange}
        searchValue={searchValue}
        onSearchChange={(val) => {
          if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
          setSearchValue(val);
        }}
        onSearch={() => handleSearch(searchValue)}
        loading={loading}
        isSearchActive={showAnimation ? animFilterBarActive : submittedQuery !== null}
        submittedCollections={showAnimation ? submittedCollections : filterBarCollections}
        visibleCollections={visibleCollections}
        onToggleVisible={handleToggleVisible}
        searchDisabled={false}
        fixedQuota={isGuest}
      />
      {rateLimitRetryAfter !== null && (
        <RateLimitModal
          limitType={rateLimitType}
          retryAfter={rateLimitRetryAfter}
          onDismiss={() => setRateLimitRetryAfter(null)}
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
