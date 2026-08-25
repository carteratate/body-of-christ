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
import { updatePreferences } from "@/lib/api";
import { useGuestGate } from "@/components/layout/guestGate";
import { saveFeedbackContext } from "@/lib/feedbackContext";
import { trackQuotaChanged } from "@/lib/analytics";
import { useAuthenticatedSearchRoute } from "@/lib/search-experience/useAuthenticatedSearchRoute";
import {
  readGuestSearch,
  useSearchPageExperience,
} from "@/lib/search-experience/useSearchPageExperience";

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

  const searchParams = useSearchParams();
  const restoreId = searchParams.get("restore");
  const exploreQuery = searchParams.get("explore");
  const exploreRef = searchParams.get("exploreRef");
  const restoredGuestSearch = useRef(isGuest ? readGuestSearch() : null);

  // ── State ─────────────────────────────────────────────────────────────────

  const [activeCollections, setActiveCollections] = useState<string[]>(() => {
    if (isGuest) return ["bible", "catechism", "church-fathers", "summa", "councils", "encyclicals"];
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
  const [visibleCollections, setVisibleCollections] = useState<string[]>(
    () => [...(restoredGuestSearch.current?.visibleCollections ?? [])],
  );
  // Measured footprint of the query bubble shown during the animation — passed to
  // LoadingAnimation so its radial constellation shrinks to never overlap the bubble.
  const [bubbleSize, setBubbleSize] = useState<{ width: number; height: number } | null>(null);
  const [showFirstSearchHint, setShowFirstSearchHint] = useState(false);
  const [showFirstContextHint, setShowFirstContextHint] = useState(false);

  // ── Abort in-flight streams on unmount ───────────────────────────────────

  const prefsSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prefsMountedRef = useRef(false);
  const bubbleRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return () => {
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

  const { experience, snapshot, view: searchView } = useSearchPageExperience({
    isGuest,
    token,
    userId,
    searches,
    translation,
    quota,
    restoredGuestSearch: restoredGuestSearch.current,
    guestGate,
    pendingHistory: {
      showPending(entryId, query) {
        setPendingSearch(entryId, query);
        setActiveSearchId(entryId);
      },
      clearPending: (entryId) => clearPendingSearch(entryId),
      activate: setActiveSearchId,
      refresh: refreshSearches,
    },
    viewSynchronization: {
      setVisibleCollections,
      clearDraft: () => setSearchValue(""),
      deactivateHistory: () => setActiveSearchId(null),
    },
    onFirstGuestSearchWithPassages: () => setShowFirstSearchHint(true),
  });
  const replaceWithSearchRoute = useCallback(() => router.replace("/search"), [router]);
  const routeSearchDefaults = useMemo(() => ({
    collections: activeCollections,
    translation,
    quota,
  }), [activeCollections, quota, translation]);
  const authenticatedRoute = useAuthenticatedSearchRoute({
    experience,
    snapshot,
    restoreId,
    userId: isGuest ? null : userId,
    credential: isGuest ? null : token,
    exploreQuery,
    exploreReference: exploreRef,
    defaults: routeSearchDefaults,
    replaceWithSearchRoute,
  });

  // On initial mount: show placeholder unless we're restoring a past search.
  const mountRestoreId = useRef(restoreId);
  useEffect(() => {
    if (isGuest || mountRestoreId.current) return;
    experience.send({ type: "prepare-pending-history" });
  }, [experience, isGuest]);

  // ── Reset on New Search ───────────────────────────────────────────────────

  const prevSearchKey = useRef(searchKey);

  useEffect(() => {
    if (prevSearchKey.current === searchKey) return;
    prevSearchKey.current = searchKey;
    experience.send({ type: "reset" });
    authenticatedRoute.cancelPendingExplore();
    setSearchValue("");
    setVisibleCollections([]);
  }, [authenticatedRoute, experience, searchKey]);

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
      setSearchValue("");
      setVisibleCollections([...searchCollections]);
      experience.send({
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
    [activeCollections, experience, quota, searchValue, translation]
  );

  // ── Animation ─────────────────────────────────────────────────────────────

  function handleAnimReadyToShow(requestId: number) {
    experience.send({
      type: "animation",
      runId: requestId,
      milestone: "ready-to-reveal",
    });
  }

  function handleAnimFiltersReady(requestId: number) {
    experience.send({
      type: "animation",
      runId: requestId,
      milestone: "filters-ready",
    });
  }

  function handleAnimFadeComplete(requestId: number) {
    experience.send({
      type: "animation",
      runId: requestId,
      milestone: "fade-complete",
    });
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
      experience.send({ type: "guest-visible-collections-changed", collections: next });
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
    const currentRequest = snapshot.status === "active-search"
      || snapshot.status === "restored-passages"
      || (snapshot.status === "failure" && snapshot.request)
      ? snapshot.request
      : null;
    const criteria = currentRequest ?? routeSearchDefaults;
    experience.send({
      type: "queue-explore",
      request: {
        query: content,
        collections: criteria.collections,
        translation: criteria.translation,
        quota: criteria.quota,
        origin: "explore",
        exploreLabel: label,
      },
    });
  }, [authenticatedRoute, experience, isGuest, routeSearchDefaults, snapshot]);

  useLayoutEffect(() => {
    if (!searchView.showAnimation || !searchView.queryBubbleVisible
      || !searchView.submittedQuery || searchView.exploreLabel) {
      setBubbleSize(null);
      return;
    }
    const el = bubbleRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (width > 0 && height > 0) setBubbleSize({ width, height });
  }, [searchView.exploreLabel, searchView.queryBubbleVisible, searchView.showAnimation, searchView.submittedQuery]);

  // Collections that actually have results — used for filter bar pills only.
  // Derived from results so it never shows buttons for collections that returned nothing.
  const filterBarCollections = useMemo(
    () => [...new Set(searchView.passages.map((passage) => passage.source.collection))],
    [searchView.passages]
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      <div className="relative flex-1 min-h-0 overflow-y-auto px-4 pt-4 pb-2">
        {/* Animation overlay — scoped to content area only, BottomBar stays visible */}
        {searchView.showAnimation && (
          <LoadingAnimation
            key={searchView.animationRunId}
            collections={searchView.submittedCollections.length > 0 ? [...searchView.submittedCollections] : activeCollections}
            quota={searchView.submittedQuota ?? quota}
            isQueryDone={searchView.queryDone}
            retrievalStarted={searchView.retrievalStarted}
            onFiltersReady={() => handleAnimFiltersReady(searchView.animationRunId)}
            onReadyToShow={() => handleAnimReadyToShow(searchView.animationRunId)}
            onFadeComplete={() => handleAnimFadeComplete(searchView.animationRunId)}
            reservedTopRight={bubbleSize}
          />
        )}

        {!searchView.submittedQuery && !searchView.loading && !searchView.error && (
          <EmptyState onSelectQuery={handleSelectQuery} />
        )}

        {/* Keep the revealed query in normal flow so results reserve its height.
            During the animation fade, z-20 places it above the z-10 overlay. */}
        {searchView.queryBubbleVisible && searchView.submittedQuery && !searchView.exploreLabel && (
          <div
            ref={bubbleRef}
            className={`relative flex justify-end mb-4 ${searchView.showAnimation ? "z-20 pointer-events-none" : ""}`}
          >
            <div className="max-w-[70%] max-md:max-w-[85%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
              {searchView.submittedQuery}
            </div>
          </div>
        )}

        {searchView.exploreLabel && (
          <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-brand-accent/10 border border-brand-accent/20">
            <Search size={14} className="text-brand-accent shrink-0" />
            <span className="text-sm text-brand-muted">
              Exploring passages related to{" "}
              <span className="text-brand-primary font-medium">{searchView.exploreLabel}</span>
            </span>
          </div>
        )}

        {!searchView.error && (searchView.loading || searchView.submittedQuery) && (
          <SearchResults
            results={[...searchView.passages]}
            loading={searchView.loading}
            searchId={searchView.searchId}
            token={token ?? ""}
            onExploreMore={handleExploreMore}
            phase={searchView.phase}
            submittedCollections={[...searchView.submittedCollections]}
            visibleCollections={visibleCollections}
            outcome={searchView.outcome}
            collectionOutcomes={{ ...searchView.collectionOutcomes }}
            isRestoring={searchView.restoring}
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

        {searchView.saveWarning && !searchView.loading && !searchView.error && (
          <div className="mt-3 rounded-lg border border-brand-accent/30 bg-brand-accent/10 px-4 py-3 text-sm text-brand-muted">
            {searchView.saveWarning}
          </div>
        )}

        {searchView.completionFailure && !searchView.completionFailure.rateLimit && !searchView.loading && (
          <div
            role="status"
            className="mt-3 rounded-lg border border-brand-accent/30 bg-brand-accent/10 px-4 py-3 text-sm text-brand-muted"
          >
            {searchView.completionFailure.message}
          </div>
        )}

        {searchView.error && !searchView.loading && (
          <SearchFailureScreen
            message={searchView.error}
            code={searchView.errorCode}
            stage={searchView.errorStage}
            onRetry={() => {
              experience.send({ type: "retry" });
            }}
            onReport={isGuest ? undefined : () => {
              const safeCode = (["auth_error", "network_error", "rate_limit", "restore_not_found", "restore_unavailable", "server_error", "stream_interrupted"] as const)
                .find((value) => value === searchView.errorCode) ?? "unknown";
              saveFeedbackContext({ category: "bug", origin: "search_error", route: "/search", search_id: searchView.searchId ?? undefined, error_code: safeCode });
              router.push("/feedback");
            }}
          />
        )}

      </div>

      <BottomBar
        activeCollections={searchView.loading && searchView.submittedCollections.length > 0 ? [...searchView.submittedCollections] : activeCollections}
        onToggleCollection={handleToggleCollection}
        translation={searchView.loading && searchView.submittedTranslation ? searchView.submittedTranslation : translation}
        onTranslationChange={setTranslation}
        quota={searchView.loading && searchView.submittedQuota !== null ? searchView.submittedQuota : quota}
        onQuotaChange={handleQuotaChange}
        searchValue={searchValue}
        onSearchChange={(val) => {
          experience.send({ type: "cancel-queued-explore" });
          authenticatedRoute.cancelPendingExplore();
          setSearchValue(val);
        }}
        onSearch={() => handleSearch(searchValue)}
        loading={searchView.loading}
        isSearchActive={searchView.showAnimation ? searchView.filterBarActive : searchView.submittedQuery !== null}
        submittedCollections={searchView.showAnimation ? [...searchView.submittedCollections] : filterBarCollections}
        visibleCollections={visibleCollections}
        onToggleVisible={handleToggleVisible}
        searchDisabled={false}
        fixedQuota={isGuest}
      />
      {searchView.rateLimit && (
        <RateLimitModal
          limitType={searchView.rateLimit.type}
          retryAfter={searchView.rateLimit.retryAfter}
          onDismiss={() => {
            experience.send({ type: "dismiss-rate-limit" });
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
