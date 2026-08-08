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
  updatePreferences,
  type ChunkResult,
  type CollectionOutcome,
  type SearchOutcome,
} from "@/lib/api";
import { markTrialUsed } from "@/lib/trial";
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

function SearchPageInner({ isGuest = false }: { isGuest?: boolean }) {
  const router = useRouter();
  const {
    token, preferences,
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
  const exploreQuery = searchParams.get("explore");
  const exploreRef = searchParams.get("exploreRef");

  // ── State ─────────────────────────────────────────────────────────────────

  const [activeCollections, setActiveCollections] = useState<string[]>(() => {
    const cols = preferences?.default_collections;
    return cols && cols.length > 0 ? cols : [];
  });
  const [translation, setTranslation] = useState<string>(() =>
    preferences?.preferred_translation || "CPDV"
  );
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
  // Starts false (search input visible), becomes true ~1.4s in (when the gold line arrives).
  const [animFilterBarActive, setAnimFilterBarActive] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [submittedCollections, setSubmittedCollections] = useState<string[]>([]);
  const [visibleCollections, setVisibleCollections] = useState<string[]>([]);
  // Measured footprint of the query bubble shown during the animation — passed to
  // LoadingAnimation so its radial constellation shrinks to never overlap the bubble.
  const [bubbleSize, setBubbleSize] = useState<{ width: number; height: number } | null>(null);
  const [guestSearchDone, setGuestSearchDone] = useState(false);

  // ── Abort in-flight streams on unmount ───────────────────────────────────

  const abortRef = useRef<AbortController | null>(null);
  const activeRequestRef = useRef(0);
  const exploreTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const filterTransitionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
      abortRef.current?.abort();
      if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
      if (filterTransitionTimerRef.current) clearTimeout(filterTransitionTimerRef.current);
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
  const exploredForQuery = useRef<string | null>(null);

  useEffect(() => {
    if (prevSearchKey.current === searchKey) return;
    prevSearchKey.current = searchKey;
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
    if (filterTransitionTimerRef.current) { clearTimeout(filterTransitionTimerRef.current); filterTransitionTimerRef.current = null; }
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
    if (!restoreId || !token) return;
    if (restoredForId.current === restoreId) return;
    const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!UUID_RE.test(restoreId)) return;

    // Entering an old conversation — remove the "New Search" placeholder
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = activeRequestRef.current + 1;
    activeRequestRef.current = requestId;
    const isCurrentRequest = () => activeRequestRef.current === requestId;
    pendingIdRef.current = null;
    clearPendingSearch();

    // Clear the currently-shown search up front so loading placeholders appear
    // immediately on click. Without this, the previous search's results (and
    // query bubble) linger until getSearchResults resolves — a visible flash of
    // stale content when switching between history items.
    setResults([]);
    setError(null);
    setErrorCode(null);
    setErrorStage(null);
    setSearchId(null);
    setOutcome(null);
    setCollectionOutcomes({});
    setSaveWarning(null);
    setQueryBubbleVisible(false);

    const id = restoreId;
    const tok = token;
    restoredForId.current = id;
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
        const storedCollections = searchesRef.current.find((s) => s.id === id)?.filters?.collections;
        const asked = Array.isArray(storedCollections)
          ? storedCollections.filter((c): c is string => typeof c === "string" && ALL_COLLECTION_KEYS.includes(c))
          : [];
        const restored = asked.length > 0
          ? asked
          : [...new Set(data.results.map((r) => r.source.collection))];
        setSubmittedCollections(restored);
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
        setError(msg);
        setErrorCode("restore_failed");
        setErrorStage("restore");
      })
      .finally(() => {
        if (!isCurrentRequest()) return;
        setLoading(false);
        setIsRestoring(false);
      });
    return () => {
      if (activeRequestRef.current === requestId) activeRequestRef.current += 1;
      controller.abort();
    };
  }, [restoreId, token, setActiveSearchId, clearPendingSearch]);

  // ── Search ────────────────────────────────────────────────────────────────

  const handleSearch = useCallback(
    async (queryOverride?: string, newExploreLabel?: string) => {
      const query = queryOverride ?? searchValue;
      if (loading || activeCollections.length === 0 || !query.trim() || guestSearchDone) return;
      const currentToken = tokenRef.current;
      if (!isGuest && !currentToken) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const requestId = activeRequestRef.current + 1;
      activeRequestRef.current = requestId;
      setAnimationRequestId(requestId);
      let terminalReceived = false;
      const isCurrentRequest = () => activeRequestRef.current === requestId;

      // Update the pending slot title from "New Search" → actual query
      const pid = pendingIdRef.current ?? crypto.randomUUID();
      pendingIdRef.current = pid;
      setPendingSearch(pid, query);
      setActiveSearchId(pid);

      bufferedChunksRef.current = [];
      bufferedExplRef.current   = {};
      resolvedRef.current = false;
      if (filterTransitionTimerRef.current) clearTimeout(filterTransitionTimerRef.current);
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
      // Switch BottomBar from search input → filter pills when the gold line fades (~3.2s)
      filterTransitionTimerRef.current = setTimeout(() => setAnimFilterBarActive(true), 3200);
      setExploreLabel(newExploreLabel ?? null);
      const snapshot = [...activeCollections];
      setSubmittedCollections(snapshot);
      setVisibleCollections(snapshot);

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
              // Consume the free trial silently — let the guest read and explore
              // the results. The signup modal is deferred until they attempt a
              // next action (New Search / nav link), handled in GuestShell.
              markTrialUsed();
              setGuestSearchDone(true);
            }
            trackSearchPerformed({
              queryLength: query.length,
              collectionsUsed: activeCollections,
              quotaPerSource: quota,
              resultCount,
              translation,
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
            query,
            { collections: activeCollections, translation },
            quota,
            streamCallbacks,
            controller.signal,
          );
        } else {
          await streamSearch(
            currentToken!,
            query,
            { collections: activeCollections, translation },
            quota,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [loading, activeCollections, translation, quota, searchValue, guestSearchDone, setPendingSearch, setActiveSearchId, clearPendingSearch]
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
    if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
    exploreTimerRef.current = setTimeout(() => {
      handleSearch(content, label);
    }, 300);
  }, [handleSearch]);

  // ── Explore flow (from ?explore= query param) ──────────────────────────────

  useEffect(() => {
    if (!exploreQuery || !token) return;
    if (exploredForQuery.current === exploreQuery) return;
    exploredForQuery.current = exploreQuery;
    const label = exploreRef?.trim()
      || (exploreQuery.slice(0, 60).replace(/\s+\S*$/, "") + (exploreQuery.length > 60 ? "…" : ""));
    const timer = setTimeout(() => {
      handleSearch(exploreQuery, label);
    }, 100);
    return () => clearTimeout(timer);
  }, [exploreQuery, exploreRef, token, handleSearch]);

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
            collections={activeCollections}
            quota={quota}
            isQueryDone={queryDone}
            retrievalStarted={searchPhase !== null || queryDone}
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
            onRetry={() => submittedQuery && handleSearch(submittedQuery)}
            onReport={isGuest ? undefined : () => {
              const safeCode = (["auth_error", "network_error", "rate_limit", "restore_unavailable", "server_error", "stream_interrupted"] as const)
                .find((value) => value === errorCode) ?? "unknown";
              saveFeedbackContext({ category: "bug", origin: "search_error", route: "/search", search_id: searchId ?? undefined, error_code: safeCode });
              router.push("/feedback");
            }}
          />
        )}

      </div>

      <BottomBar
        activeCollections={activeCollections}
        onToggleCollection={handleToggleCollection}
        translation={translation}
        onTranslationChange={setTranslation}
        quota={quota}
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
        searchDisabled={guestSearchDone}
        fixedQuota={isGuest}
      />
      <RateLimitModal
        isOpen={rateLimitRetryAfter !== null}
        limitType={rateLimitType}
        retryAfter={rateLimitRetryAfter}
        onDismiss={() => setRateLimitRetryAfter(null)}
      />
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
