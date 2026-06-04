"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { BottomBar } from "@/components/search/BottomBar";
import { EmptyState } from "@/components/search/EmptyState";
import { SearchResults } from "@/components/search/SearchResults";
import { RateLimitModal } from "@/components/common";
import { ALL_COLLECTION_KEYS } from "@/lib/collections";
import {
  streamSearch,
  getSearchResults,
  type ChunkResult,
} from "@/lib/api";
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

function SearchPageInner() {
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
    return cols && cols.length > 0 ? cols : ALL_COLLECTION_KEYS;
  });
  const [translation, setTranslation] = useState<string>(() =>
    preferences?.preferred_translation || "CPDV"
  );
  const [quota, setQuota] = useState<number>(() =>
    preferences?.default_quota ?? 4
  );
  const [searchValue, setSearchValue] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [results, setResults] = useState<ChunkResult[]>([]);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rateLimitRetryAfter, setRateLimitRetryAfter] = useState<number | null>(null);
  const [rateLimitType, setRateLimitType] = useState<"per_minute" | "daily">("per_minute");
  const [searchPhase, setSearchPhase] = useState<"searching" | "ranking" | null>(null);
  const [exploreLabel, setExploreLabel] = useState<string | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);

  // ── Abort in-flight streams on unmount ───────────────────────────────────

  const abortRef = useRef<AbortController | null>(null);
  const exploreTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
    };
  }, []);

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
    setSearchId(null);
    setError(null);
    setLoading(false);
    setSearchValue("");
    setSearchPhase(null);
    setRateLimitRetryAfter(null);
    setExploreLabel(null);
    setIsRestoring(false);
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
        setSearchValue(data.query);
        setActiveSearchId(id);
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
      if (loading || activeCollections.length === 0 || !query.trim()) return;
      const currentToken = tokenRef.current;
      if (!currentToken) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      // Update the pending slot title from "New Search" → actual query
      const pid = pendingIdRef.current ?? crypto.randomUUID();
      pendingIdRef.current = pid;
      setPendingSearch(pid, query);
      setActiveSearchId(pid);

      setLoading(true);
      setSearchPhase(null);
      setError(null);
      setRateLimitRetryAfter(null);
      setRateLimitType("per_minute");
      setSubmittedQuery(query);
      setSearchValue("");
      setResults([]);
      setExploreLabel(newExploreLabel ?? null);

      try {
        await streamSearch(
          currentToken,
          query,
          { collections: activeCollections, translation },
          quota,
          {
            onStatus(phase) {
              setSearchPhase(phase);
            },
            onChunk(chunk) {
              setResults((prev) => [...prev, { ...chunk, explanation: null }]);
            },
            onExplanationDelta(chunkId, delta) {
              setResults((prev) =>
                prev.map((r) =>
                  r.chunk_id === chunkId
                    ? { ...r, explanation: (r.explanation ?? "") + delta }
                    : r
                )
              );
            },
            onDone(sid, resultCount) {
              setSearchPhase(null);
              setSearchId(sid);
              setLoading(false);
              // Search is now saved in DB — replace pending slot with real entry
              pendingIdRef.current = null;
              clearPendingSearch();
              if (sid) {
                setActiveSearchId(sid);
                refreshSearchesRef.current();
              }
              trackSearchPerformed({
                queryLength: query.length,
                collectionsUsed: activeCollections,
                quotaPerSource: quota,
                resultCount,
                translation,
              });
            },
            onError(msg) {
              setSearchPhase(null);
              setError(msg);
              setLoading(false);
              // Keep the pending slot — user is still in this fresh-search state
              trackErrorOccurred({ page: "search", errorType: classifyError(msg) });
            },
            onRateLimit(retryAfter, limitType) {
              setSearchPhase(null);
              setRateLimitRetryAfter(retryAfter ?? 60);
              setRateLimitType(limitType);
              setLoading(false);
            },
          },
          controller.signal
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Search failed";
        setError(msg);
        setLoading(false);
        trackErrorOccurred({ page: "search", errorType: classifyError(msg) });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [loading, activeCollections, translation, quota, searchValue, setPendingSearch, setActiveSearchId, clearPendingSearch]
  );

  // ── Handlers ──────────────────────────────────────────────────────────────

  function handleToggleCollection(c: string) {
    setActiveCollections((prev) =>
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

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-4 pt-4 pb-2">
        {!submittedQuery && !loading && !error && (
          <EmptyState onSelectQuery={handleSelectQuery} />
        )}

        {submittedQuery && !exploreLabel && (
          <div className="flex justify-end mb-4">
            <div className="max-w-[70%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
              {submittedQuery}
            </div>
          </div>
        )}

        {exploreLabel && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-brand-accent/10 border border-brand-accent/20">
            <span className="text-brand-accent text-sm">🔍</span>
            <span className="text-sm text-brand-muted">
              Exploring passages related to{" "}
              <span className="text-brand-primary font-medium">{exploreLabel}</span>
            </span>
          </div>
        )}

        {(loading || results.length > 0) && (
          <SearchResults
            results={results}
            loading={loading}
            searchId={searchId}
            token={token ?? ""}
            onExploreMore={handleExploreMore}
            phase={searchPhase}
            collections={activeCollections}
            isRestoring={isRestoring}
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

        {!loading && !error && submittedQuery && results.length === 0 && searchId && (
          <p className="text-brand-muted text-sm text-center py-8">
            No passages found for your query in the selected sources. Try enabling more
            collections or rephrasing your question.
          </p>
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

export function SearchPage() {
  return (
    <Suspense>
      <SearchPageInner />
    </Suspense>
  );
}
