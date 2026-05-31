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
  updatePreferences,
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
  const { token, preferences } = useAppContext();
  const tokenRef = useRef(token);
  useEffect(() => {
    tokenRef.current = token;
  });

  const searchParams = useSearchParams();
  const restoreId = searchParams.get("restore");
  const exploreQuery = searchParams.get("explore");

  // ── State ─────────────────────────────────────────────────────────────────

  const [activeCollections, setActiveCollections] = useState<string[]>(ALL_COLLECTION_KEYS);
  const [translation, setTranslation] = useState<string>("CPDV");
  const [quota, setQuota] = useState<number>(4);
  const [searchValue, setSearchValue] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [results, setResults] = useState<ChunkResult[]>([]);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rateLimitRetryAfter, setRateLimitRetryAfter] = useState<number | null>(null);
  const [rateLimitType, setRateLimitType] = useState<"per_minute" | "daily">("per_minute");

  // ── Preferences init (once) ───────────────────────────────────────────────

  const prefInitialized = useRef(false);

  useEffect(() => {
    if (prefInitialized.current || !preferences) return;
    prefInitialized.current = true;
    setActiveCollections(
      preferences.default_collections.length > 0
        ? preferences.default_collections
        : ALL_COLLECTION_KEYS
    );
    setTranslation(preferences.preferred_translation || "CPDV");
    setQuota(preferences.default_quota ?? 4);
  }, [preferences]);

  // ── Quota persistence (debounced, skip mount) ─────────────────────────────

  const quotaMounted = useRef(false);

  useEffect(() => {
    if (!quotaMounted.current) {
      quotaMounted.current = true;
      return;
    }
    if (!tokenRef.current) return;
    const timer = setTimeout(() => {
      updatePreferences(tokenRef.current!, { default_quota: quota }).catch(() => {});
    }, 500);
    return () => clearTimeout(timer);
  }, [quota]);

  // ── Abort in-flight streams on unmount ───────────────────────────────────

  const abortRef = useRef<AbortController | null>(null);
  const exploreTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
    };
  }, []);

  // ── Restore flow ──────────────────────────────────────────────────────────

  const restoredForId = useRef<string | null>(null);
  const exploredForQuery = useRef<string | null>(null);

  useEffect(() => {
    if (!restoreId || !token) return;
    if (restoredForId.current === restoreId) return;
    const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!UUID_RE.test(restoreId)) return;
    restoredForId.current = restoreId;
    setLoading(true);
    getSearchResults(token, restoreId)
      .then((data) => {
        setResults(data.results);
        setSearchId(data.search_id);
        setSubmittedQuery(data.query);
        setSearchValue(data.query);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "Failed to restore search";
        setError(msg);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [restoreId, token]);

  // ── Search ────────────────────────────────────────────────────────────────

  const handleSearch = useCallback(
    async (queryOverride?: string) => {
      const query = queryOverride ?? searchValue;
      if (loading || activeCollections.length === 0 || !query.trim()) return;
      const currentToken = tokenRef.current;
      if (!currentToken) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);
      setRateLimitRetryAfter(null);
      setRateLimitType("per_minute");
      setSubmittedQuery(query);
      setResults([]);

      try {
        await streamSearch(
          currentToken,
          query,
          { collections: activeCollections, translation },
          quota,
          {
            onChunk(chunk) {
              setResults((prev) => [...prev, { ...chunk, explanation: null }]);
            },
            onExplanation(chunkId, explanation) {
              setResults((prev) =>
                prev.map((r) =>
                  r.chunk_id === chunkId ? { ...r, explanation } : r
                )
              );
            },
            onDone(sid, resultCount) {
              setSearchId(sid);
              setLoading(false);
              trackSearchPerformed({
                queryLength: query.length,
                collectionsUsed: activeCollections,
                quotaPerSource: quota,
                resultCount,
                translation,
              });
            },
            onError(msg) {
              setError(msg);
              setLoading(false);
              trackErrorOccurred({ page: "search", errorType: classifyError(msg) });
            },
            onRateLimit(retryAfter, limitType) {
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
    [loading, activeCollections, translation, quota, searchValue]
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

  const handleExploreMore = useCallback((content: string) => {
    if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
    setSearchValue(content);
    exploreTimerRef.current = setTimeout(() => {
      handleSearch(content);
    }, 300);
  }, [handleSearch]);

  // ── Explore flow (from ?explore= query param) ──────────────────────────────

  useEffect(() => {
    if (!exploreQuery || !token) return;
    if (exploredForQuery.current === exploreQuery) return;
    exploredForQuery.current = exploreQuery;
    setSearchValue(exploreQuery);
    // Auto-submit after brief delay (same as handleExploreMore)
    const timer = setTimeout(() => {
      handleSearch(exploreQuery);
    }, 100);
    return () => clearTimeout(timer);
  }, [exploreQuery, token, handleSearch]);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      {/* Results area — scrollable */}
      <div className="flex-1 overflow-y-auto px-4 pt-4 pb-2">
        {/* Empty state */}
        {!submittedQuery && !loading && !error && (
          <EmptyState onSelectQuery={handleSelectQuery} />
        )}

        {/* Submitted query bubble */}
        {submittedQuery && (
          <div className="flex justify-end mb-4">
            <div className="max-w-[70%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
              {submittedQuery}
            </div>
          </div>
        )}

        {/* Search results (skeleton while loading with no results, cards once streaming) */}
        {(loading || results.length > 0) && (
          <SearchResults
            results={results}
            loading={loading}
            searchId={searchId}
            token={token ?? ""}
            onExploreMore={handleExploreMore}
          />
        )}

        {/* Error state */}
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

        {/* No results state */}
        {!loading && !error && submittedQuery && results.length === 0 && searchId && (
          <p className="text-brand-muted text-sm text-center py-8">
            No passages found for your query in the selected sources. Try enabling more
            collections or rephrasing your question.
          </p>
        )}

      </div>

      {/* Fixed bottom bar */}
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
