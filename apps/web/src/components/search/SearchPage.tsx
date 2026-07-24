"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, Suspense } from "react";
import { Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { BottomBar } from "@/components/search/BottomBar";
import { EmptyState } from "@/components/search/EmptyState";
import { SearchResults } from "@/components/search/SearchResults";
import { LoadingAnimation } from "@/components/search/LoadingAnimation";
import { RateLimitModal } from "@/components/common";
import { ALL_COLLECTION_KEYS } from "@/lib/collections";
import {
  streamSearch,
  streamGuestSearch,
  getSearchResults,
  updatePreferences,
  type ChunkResult,
} from "@/lib/api";
import { markTrialUsed } from "@/lib/trial";
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
  const {
    token, preferences,
    searchKey,
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
  const [rateLimitRetryAfter, setRateLimitRetryAfter] = useState<number | null>(null);
  const [rateLimitType, setRateLimitType] = useState<"per_minute" | "daily">("per_minute");
  const [searchPhase, setSearchPhase] = useState<"searching" | "ranking" | null>(null);
  const [exploreLabel, setExploreLabel] = useState<string | null>(null);
  const [showAnimation, setShowAnimation] = useState(false);
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
    if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
    setResults([]);
    setSubmittedQuery(null);
    setQueryBubbleVisible(false);
    setSearchId(null);
    setError(null);
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

  useEffect(() => {
    if (!restoreId || !token) return;
    if (restoredForId.current === restoreId) return;
    const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!UUID_RE.test(restoreId)) return;

    // Entering an old conversation — remove the "New Search" placeholder
    pendingIdRef.current = null;
    clearPendingSearch();

    const id = restoreId;
    const tok = token;
    restoredForId.current = id;
    setLoading(true);
    setIsRestoring(true);
    getSearchResults(tok, id)
      .then((data) => {
        setResults(data.results);
        setSearchId(data.search_id);
        setSubmittedQuery(data.query);
        setQueryBubbleVisible(true);
        setSearchValue(data.query);
        setActiveSearchId(id);
        setSubmittedCollections(ALL_COLLECTION_KEYS);
        setVisibleCollections(ALL_COLLECTION_KEYS);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "Failed to restore search";
        setError(msg);
      })
      .finally(() => { setLoading(false); setIsRestoring(false); });
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
            setSearchPhase(phase);
          },
          onChunk(chunk: ChunkResult) {
            bufferedChunksRef.current.push({ ...chunk, explanation: null });
          },
          onExplanationDelta(chunkId: string, delta: string) {
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
          onDone(sid: string, resultCount: number) {
            setSearchPhase(null);
            setSearchId(sid);
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
          onError(msg: string) {
            setSearchPhase(null);
            setError(msg);
            setLoading(false);
            setShowAnimation(false);
            setAnimFilterBarActive(false);
            setQueryBubbleVisible(true);
            trackErrorOccurred({ page: "search", errorType: classifyError(msg) });
          },
          onRateLimit(retryAfter: number | null, limitType: "per_minute" | "daily") {
            setSearchPhase(null);
            setRateLimitRetryAfter(retryAfter ?? 60);
            setRateLimitType(limitType);
            setLoading(false);
            setShowAnimation(false);
            setAnimFilterBarActive(false);
            setQueryBubbleVisible(true);
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
        const msg = err instanceof Error ? err.message : "Search failed";
        setError(msg);
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

  function handleAnimReadyToShow() {
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

  function handleAnimFadeComplete() {
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
    <div className="flex flex-col h-full">
      <div className="relative flex-1 overflow-y-auto px-4 pt-4 pb-2">
        {/* Animation overlay — scoped to content area only, BottomBar stays visible */}
        {showAnimation && (
          <LoadingAnimation
            collections={activeCollections}
            quota={quota}
            isQueryDone={queryDone}
            retrievalStarted={searchPhase !== null || queryDone}
            onReadyToShow={handleAnimReadyToShow}
            onFadeComplete={handleAnimFadeComplete}
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

        {(loading || submittedQuery) && (
          <SearchResults
            results={results}
            loading={loading}
            searchId={searchId}
            token={token ?? ""}
            onExploreMore={handleExploreMore}
            phase={searchPhase}
            submittedCollections={submittedCollections}
            visibleCollections={visibleCollections}
            isRestoring={isRestoring}
            isGuest={isGuest}
          />
        )}

        {error && !loading && (
          <div className="text-center py-8">
            <p className="text-brand-muted text-sm mb-3">Search failed. Please try again.</p>
            <button
              onClick={() => submittedQuery && handleSearch(submittedQuery)}
              className="text-brand-accent text-sm hover:underline"
            >
              Retry
            </button>
          </div>
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
          exploreTimerRef.current && clearTimeout(exploreTimerRef.current);
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
