"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { useAppContext } from "@/components/layout/AppShell";
import { Toast, useToast } from "@/components/common";
import { getSearchHistoryPage, type SearchSummaryV2 } from "@/lib/api";
import { HistorySearchRow } from "./HistorySearchRow";
import { groupSearchesByLocalDate } from "./historyGroups";
import { useSearchDeletion } from "./useSearchDeletion";
import { useRestorePrefetch } from "./useRestorePrefetch";
import { HistorySkeleton } from "@/components/common/PageSkeletons";

// AppShell loads the first page before any page renders, so on a full load of
// /history its list is moments old; refreshing it again would repeat the request.
const SEED_FRESH_MS = 10_000;

export function HistoryPage() {
  const {
    token,
    pendingSearch,
    activeSearchId,
    removeSearch,
    searches: shellSearches,
    searchHistoryCursor,
    searchHistoryLoadedAt,
  } = useAppContext();
  const seeded = searchHistoryLoadedAt !== null;
  // Arriving from elsewhere in the app, AppShell already holds the first page:
  // show it at once and refresh it in the background instead of a skeleton.
  const [searches, setSearches] = useState<SearchSummaryV2[]>(() => (seeded ? shellSearches : []));
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(() => (seeded ? searchHistoryCursor : null));
  const [loading, setLoading] = useState(!seeded);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [revealedId, setRevealedId] = useState<string | null>(null);
  const { toast, showToast, dismissToast } = useToast();
  const requestGeneration = useRef(0);
  const appliedQueryRef = useRef("");
  // The query whose results are on screen; null while none are.
  const shownQueryRef = useRef<string | null>(seeded ? "" : null);
  const seedLoadedAtRef = useRef(searchHistoryLoadedAt);
  // Searches deleted here while a refresh was in flight; its response predates
  // the delete and must not bring them back.
  const deletedIdsRef = useRef(new Set<string>());
  // Requests read the token through a ref so a routine token refresh does not
  // reload the page.
  const tokenRef = useRef(token);
  const signedIn = Boolean(token);
  const prefetch = useRestorePrefetch();

  useEffect(() => { tokenRef.current = token; }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => setAppliedQuery(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    appliedQueryRef.current = appliedQuery;
  }, [appliedQuery]);

  useEffect(() => {
    const requestToken = tokenRef.current;
    if (!signedIn || !requestToken) return;
    const seedLoadedAt = seedLoadedAtRef.current;
    seedLoadedAtRef.current = null;
    if (seedLoadedAt !== null && !appliedQuery && reloadKey === 0 && Date.now() - seedLoadedAt < SEED_FRESH_MS) return;
    const generation = ++requestGeneration.current;
    let alive = true;
    // Results already showing for this query stay up while they are refreshed;
    // a failed refresh keeps them rather than replacing them with an error.
    const background = shownQueryRef.current === appliedQuery;
    if (background) setRefreshing(true);
    else setLoading(true);
    setLoadingMore(false);
    setError(false);
    getSearchHistoryPage(requestToken, { query: appliedQuery || undefined })
      .then((page) => {
        if (!alive || generation !== requestGeneration.current) return;
        setSearches(page.searches.filter((search) => !deletedIdsRef.current.has(search.id)));
        setNextCursor(page.next_cursor);
        shownQueryRef.current = appliedQuery;
      })
      .catch(() => {
        if (!alive || generation !== requestGeneration.current || background) return;
        shownQueryRef.current = null;
        setError(true);
      })
      .finally(() => {
        if (!alive || generation !== requestGeneration.current) return;
        setLoading(false);
        setRefreshing(false);
      });
    return () => { alive = false; };
  }, [signedIn, appliedQuery, reloadKey]);

  useEffect(() => {
    if (!revealedId) return;
    function closeOutside(event: PointerEvent) {
      const row = (event.target as Element | null)?.closest?.("[data-history-row]");
      if (row?.getAttribute("data-history-row") !== revealedId) setRevealedId(null);
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [revealedId]);

  function removeLocally(id: string) {
    deletedIdsRef.current.add(id);
    setRevealedId(null);
    setSearches((current) => current.filter((search) => search.id !== id));
  }

  function restoreLocally(search: SearchSummaryV2, index: number) {
    deletedIdsRef.current.delete(search.id);
    const currentQuery = appliedQueryRef.current.toLocaleLowerCase();
    if (currentQuery && !search.query.toLocaleLowerCase().includes(currentQuery)) {
      setReloadKey((key) => key + 1);
      return;
    }
    setSearches((current) => {
      if (current.some((item) => item.id === search.id)) return current;
      const next = [...current];
      next.splice(Math.min(index, next.length), 0, search);
      return next;
    });
  }

  const { deletingId, deleteById } = useSearchDeletion({
    searches,
    removeLocally,
    restoreLocally,
    // The page row is removed optimistically above. Once the API confirms the
    // deletion, update AppShell's sidebar cache in place instead of invalidating
    // this page and replacing it with a full loading skeleton.
    onSuccess: removeSearch,
    showToast,
    focusAfterRemove: (index) => {
      requestAnimationFrame(() => {
        const rows = document.querySelectorAll<HTMLElement>("#history-results [data-history-row] a");
        rows[Math.min(index, rows.length - 1)]?.focus();
        if (rows.length === 0) document.getElementById("history-search-input")?.focus();
      });
    },
    focusAfterRestore: (id) => {
      requestAnimationFrame(() => {
        const row = Array.from(document.querySelectorAll<HTMLElement>("#history-results [data-history-row]"))
          .find((item) => item.dataset.historyRow === id);
        row?.querySelector<HTMLElement>("a")?.focus();
      });
    },
  });

  async function loadMore() {
    // A refresh in flight would replace the list with its first page; continue
    // from its cursor once it lands rather than racing it.
    if (!token || !nextCursor || loadingMore || refreshing) return;
    const generation = requestGeneration.current;
    const queryAtRequest = appliedQueryRef.current;
    setLoadingMore(true);
    try {
      const page = await getSearchHistoryPage(token, {
        cursor: nextCursor,
        query: queryAtRequest || undefined,
      });
      if (generation !== requestGeneration.current || queryAtRequest !== appliedQueryRef.current) return;
      setSearches((current) => {
        const existing = new Set(current.map((search) => search.id));
        return [...current, ...page.searches.filter((search) => !existing.has(search.id))];
      });
      setNextCursor(page.next_cursor);
    } catch {
      if (generation === requestGeneration.current) showToast("Couldn't load more history.", "error");
    } finally {
      if (generation === requestGeneration.current) setLoadingMore(false);
    }
  }

  const groups = useMemo(() => groupSearchesByLocalDate(searches), [searches]);

  if (loading) return <HistorySkeleton />;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-3xl px-4 py-5 sm:px-6 sm:py-7">
        <div className="mb-5">
          <h1 className="text-2xl font-semibold text-brand-primary">Search History</h1>
          <p className="mt-1 text-sm text-brand-muted">Return to previous questions and their sources.</p>
        </div>

        <label className="mb-6 flex items-center gap-2 rounded-md border border-brand-muted/30 bg-brand-surface px-3 focus-within:border-brand-accent">
          <Search size={17} className="shrink-0 text-brand-muted" aria-hidden="true" />
          <span className="sr-only">Search your history</span>
          <input
            id="history-search-input"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search your history"
            className="min-w-0 flex-1 bg-transparent py-3 text-brand-primary outline-none placeholder:text-brand-muted"
          />
        </label>

        {pendingSearch && !appliedQuery && (
          <section className="mb-6" aria-labelledby="history-in-progress">
            <h2 id="history-in-progress" className="mb-2 text-xs font-semibold uppercase tracking-widest text-brand-muted">In progress</h2>
            <div className="rounded-md bg-brand-surface px-3 py-3 text-sm text-brand-accent">{pendingSearch.query}</div>
          </section>
        )}

        {!loading && error && (
          <div className="py-12 text-center">
            <p className="mb-3 text-sm text-brand-muted">Your history couldn&apos;t be loaded.</p>
            <button onClick={() => setReloadKey((key) => key + 1)} className="text-sm text-brand-accent hover:underline">Try again</button>
          </div>
        )}
        {!loading && !error && groups.length === 0 && (
          <p className="py-12 text-center text-sm text-brand-muted">
            {appliedQuery ? "No searches match that phrase." : "Your completed searches will appear here."}
          </p>
        )}

        <div id="history-results">
        {!loading && !error && groups.map((group) => (
          <section key={group.label} className="mb-7" aria-labelledby={`history-${group.label.toLowerCase()}`}>
            <h2 id={`history-${group.label.toLowerCase()}`} className="mb-2 text-xs font-semibold uppercase tracking-widest text-brand-muted">{group.label}</h2>
            <div className="space-y-2">
              {group.searches.map((search) => (
                <HistorySearchRow
                  key={search.id}
                  search={search}
                  active={search.id === activeSearchId}
                  revealed={revealedId === search.id}
                  deleting={deletingId === search.id}
                  showDate={group.showDate}
                  onIntent={() => prefetch.schedule(search)}
                  onIntentEnd={prefetch.cancel}
                  onReveal={() => setRevealedId(search.id)}
                  onClose={() => setRevealedId(null)}
                  onDelete={() => void deleteById(search.id)}
                />
              ))}
            </div>
          </section>
        ))}
        </div>

        {!loading && !error && nextCursor && (
          <div className="pb-8 text-center">
            <button
              type="button"
              onClick={() => void loadMore()}
              disabled={loadingMore || refreshing}
              className="rounded-md border border-brand-accent px-4 py-2 text-sm text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg disabled:opacity-50"
            >
              {loadingMore ? "Loading…" : "Load older searches"}
            </button>
          </div>
        )}
      </div>
      {toast.visible && <Toast message={toast.message} type={toast.type} onDismiss={dismissToast} />}
    </div>
  );
}
