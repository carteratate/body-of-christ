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
import {
  type ActiveSearchSnapshot,
  type FailureSnapshot,
} from "@/lib/search-experience";
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

  const { experience, snapshot } = useSearchPageExperience({
    isGuest,
    token,
    userId,
    searches,
    translation,
    quota,
    restoredGuestSearch: restoredGuestSearch.current,
    guestGate,
    setPendingSearch,
    clearPendingSearch,
    setActiveSearchId,
    refreshSearches,
    onFirstGuestSearchWithResults: () => setShowFirstSearchHint(true),
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
    experience.send({
      type: "queue-explore",
      request: {
        query: content,
        collections: activeCollections,
        translation,
        quota,
        origin: "explore",
        exploreLabel: label,
      },
    });
  }, [activeCollections, authenticatedRoute, experience, isGuest, quota, translation]);

  const runtimeActive: ActiveSearchSnapshot | null = snapshot.status === "active-search"
    ? snapshot
    : null;
  const runtimeRestored = snapshot.status === "restored-results"
    ? snapshot
    : null;
  const runtimeRestoring = snapshot.status === "restoring";
  const runtimeFailure: FailureSnapshot | null = snapshot.status === "failure"
    ? snapshot
    : null;
  const runtimeRequest = runtimeActive?.request
    ?? runtimeRestored?.request
    ?? runtimeFailure?.request
    ?? null;
  const runtimeTransport = runtimeActive?.transport ?? null;
  const renderedLoading = runtimeRestoring || runtimeActive?.presentation.status === "animating";
  const renderedPassages = useMemo(
    () => [...(runtimeActive?.passages ?? runtimeRestored?.passages ?? [])],
    [runtimeActive?.passages, runtimeRestored?.passages],
  );
  const renderedSearchId = runtimeRestored?.searchId
    ?? (runtimeTransport?.status === "complete" ? runtimeTransport.searchId : null);
  const renderedSubmittedQuery = runtimeRequest?.query ?? null;
  const renderedQueryBubbleVisible = runtimeRestored !== null
    || (runtimeFailure?.request !== null && runtimeFailure?.request !== undefined)
    || (runtimeActive !== null && runtimeActive.presentation.status !== "animating");
  const renderedError = runtimeFailure?.failure.message ?? null;
  const renderedErrorCode = runtimeFailure?.failure.code ?? null;
  const renderedErrorStage = runtimeFailure?.failure.stage ?? null;
  const renderedOutcome = runtimeRestored
    ? runtimeRestored.passages.length > 0 ? "success" : "no_candidates"
    : runtimeTransport?.status === "complete" ? runtimeTransport.outcome : null;
  const runtimeCompletionFailure = runtimeTransport?.status === "ranked-ready"
    ? runtimeTransport.completionFailure
    : null;
  const renderedCollectionOutcomes = runtimeFailure?.failure.collectionOutcomes
    ?? runtimeCompletionFailure?.collectionOutcomes
    ?? (runtimeTransport?.status === "complete" ? runtimeTransport.collectionOutcomes : {});
  const renderedSaveWarning = runtimeRestored?.warning ?? runtimeActive?.saveWarning ?? null;
  const renderedSearchPhase = runtimeTransport?.status === "searching" ? runtimeTransport.phase : null;
  const renderedExploreLabel = runtimeRequest?.exploreLabel ?? null;
  const renderedShowAnimation = runtimeActive !== null
    && runtimeActive.presentation.status !== "revealed";
  const renderedAnimationRequestId = snapshot.runId;
  const renderedQueryDone = runtimeActive?.presentation.status === "animating"
    && runtimeActive.presentation.resultsReady;
  const renderedRetrievalStarted = runtimeTransport !== null
    && runtimeTransport.status !== "preparing";
  const renderedFilterBarActive = runtimeActive?.presentation.filtersReady ?? false;
  const renderedSubmittedCollections = [...(runtimeRequest?.collections ?? [])];
  const renderedSubmittedTranslation = runtimeRequest?.translation ?? "";
  const renderedSubmittedQuota = runtimeRequest?.quota ?? null;
  const renderedRateLimit = runtimeFailure?.failure.rateLimit?.open
    ? runtimeFailure.failure.rateLimit
    : runtimeCompletionFailure?.rateLimit?.open
      ? runtimeCompletionFailure.rateLimit
      : null;
  const visibleCollectionsRun = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (isGuest) return;
    if (runtimeActive && visibleCollectionsRun.current !== runtimeActive.runId) {
      visibleCollectionsRun.current = runtimeActive.runId;
      setVisibleCollections([...runtimeActive.request.collections]);
      return;
    }
    if (runtimeRestored) {
      visibleCollectionsRun.current = runtimeRestored.runId;
      setVisibleCollections([...runtimeRestored.request.collections]);
      return;
    }
    if (runtimeRestoring || runtimeFailure?.failure.kind === "restore") {
      visibleCollectionsRun.current = snapshot.runId;
      setVisibleCollections([]);
      setActiveSearchId(null);
      if (runtimeRestoring) setSearchValue("");
    }
  }, [isGuest, runtimeActive, runtimeFailure?.failure.kind, runtimeRestored, runtimeRestoring, setActiveSearchId, snapshot.runId]);

  useLayoutEffect(() => {
    if (!renderedShowAnimation || !renderedQueryBubbleVisible
      || !renderedSubmittedQuery || renderedExploreLabel) {
      setBubbleSize(null);
      return;
    }
    const el = bubbleRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (width > 0 && height > 0) setBubbleSize({ width, height });
  }, [renderedShowAnimation, renderedQueryBubbleVisible, renderedSubmittedQuery, renderedExploreLabel]);

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
              experience.send({ type: "retry" });
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
          experience.send({ type: "cancel-queued-explore" });
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
      {renderedRateLimit && (
        <RateLimitModal
          limitType={renderedRateLimit.type}
          retryAfter={renderedRateLimit.retryAfter}
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
