"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { BottomBar } from "@/components/search/BottomBar";
import { EmptyState } from "@/components/search/EmptyState";
import { ALL_COLLECTION_KEYS } from "@/lib/collections";
import {
  streamSearch,
  getSearchResults,
  updatePreferences,
  type ChunkResult,
} from "@/lib/api";
import {
  trackSearchPerformed,
  trackRateLimitHit,
  trackErrorOccurred,
  trackQuotaChanged,
} from "@/lib/analytics";

function SearchPageInner() {
  const { token, preferences } = useAppContext();
  const tokenRef = useRef(token);
  useEffect(() => {
    tokenRef.current = token;
  });

  const searchParams = useSearchParams();
  const restoreId = searchParams.get("restore");

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

  // ── Restore flow ──────────────────────────────────────────────────────────

  const restored = useRef(false);

  useEffect(() => {
    if (restored.current || !restoreId || !token) return;
    restored.current = true;
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

      setLoading(true);
      setError(null);
      setRateLimitRetryAfter(null);
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
              trackErrorOccurred({ page: "search", errorType: msg });
            },
            onRateLimit(retryAfter) {
              setRateLimitRetryAfter(retryAfter ?? 60);
              setLoading(false);
              trackRateLimitHit({ limitType: "per_minute" });
            },
          }
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Search failed";
        setError(msg);
        setLoading(false);
        trackErrorOccurred({ page: "search", errorType: msg });
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

        {/* Loading placeholder */}
        {loading && results.length === 0 && (
          <div className="text-brand-muted text-sm text-center py-8">Searching...</div>
        )}

        {/* Results list */}
        {results.length > 0 && (
          <div className="space-y-3">
            {/* Placeholder: Task 25 will replace with ChunkCard components */}
            {results.map((r) => (
              <div
                key={r.chunk_id}
                className="rounded-lg bg-brand-surface p-3 text-xs text-brand-muted border-l-2 border-brand-accent"
              >
                <div className="text-brand-primary text-sm mb-1">
                  {r.source.reference ?? r.source.document_title}
                </div>
                <p className="line-clamp-3">{r.content}</p>
                {r.explanation && (
                  <p className="mt-2 text-brand-muted italic">{r.explanation}</p>
                )}
              </div>
            ))}
          </div>
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

        {/* Rate limit */}
        {rateLimitRetryAfter !== null && !loading && (
          <div className="text-center py-8">
            <p className="text-brand-muted text-sm">
              Search limit reached. Try again in {rateLimitRetryAfter} seconds.
            </p>
          </div>
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
        onSearchChange={setSearchValue}
        onSearch={() => handleSearch(searchValue)}
        loading={loading}
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
