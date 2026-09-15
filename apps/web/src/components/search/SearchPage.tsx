"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { BottomBar } from "@/components/search/BottomBar";
import { EmptyState } from "@/components/search/EmptyState";
import { SearchResults } from "@/components/search/SearchResults";
import { LoadingAnimation } from "@/components/search/LoadingAnimation";
import { SearchFailureScreen } from "@/components/search/SearchFailureScreen";
import { RateLimitModal } from "@/components/common";
import { updatePreferences } from "@/lib/api";
import { createPreferenceWriter } from "@/lib/preference-writer";
import { getGuestPreferenceDraft, saveGuestPreferenceDraft } from "@/lib/trial";
import {
  createSearchDraft,
  DEFAULT_GUEST_SEARCH_PREFERENCES,
  transitionSearchDraft,
  type SearchDraft,
} from "@/lib/search-draft";
import { useGuestGate } from "@/components/layout/guestGate";
import { saveFeedbackContext } from "@/lib/feedbackContext";
import { trackCollectionToggled, trackQuotaChanged } from "@/lib/analytics";
import { useAuthenticatedSearchRoute } from "@/lib/search-experience/useAuthenticatedSearchRoute";
import {
  readGuestSearch,
  useSearchPageExperience,
} from "@/lib/search-experience/useSearchPageExperience";

function SearchPageInner({ isGuest = false }: { isGuest?: boolean }) {
  const router = useRouter();
  const guestGate = useGuestGate();
  const {
    token, userId, preferences, setPreferences,
    searchKey,
    searches,
    setActiveSearchId,
    setPendingSearch, clearPendingSearch,
    refreshSearches,
  } = useAppContext();

  const searchParams = useSearchParams();
  const restoreId = searchParams.get("restore");
  const [restoredGuestSearch] = useState(() => isGuest ? readGuestSearch() : null);
  const [guestPreferences] = useState(() => isGuest ? getGuestPreferenceDraft() : null);
  const [preferenceSaveStatus, setPreferenceSaveStatus] = useState<{
    phase: "pending" | "saving" | "saved" | "failed" | null;
    revision: number;
  }>({ phase: null, revision: 0 });

  // ── State ─────────────────────────────────────────────────────────────────

  const [draft, setDraft] = useState(() => createSearchDraft(
    isGuest
      ? guestPreferences!
      : preferences ?? {
          ...DEFAULT_GUEST_SEARCH_PREFERENCES,
          default_quota: 4,
          last_standard_quota: 4,
        },
  ));
  const activeCollections = draft.collections;
  const translation = draft.translation;
  const quota = draft.quota;
  const [searchValue, setSearchValue] = useState<string>("");
  const [visibleCollections, setVisibleCollections] = useState<string[]>(
    () => [...(restoredGuestSearch?.visibleCollections ?? [])],
  );
  // Measured footprint of the query bubble shown during the animation — passed to
  // LoadingAnimation so its radial constellation shrinks to never overlap the bubble.
  const [bubbleSize, setBubbleSize] = useState<{ width: number; height: number } | null>(null);
  const [showFirstSearchHint, setShowFirstSearchHint] = useState(false);
  const [showFirstContextHint, setShowFirstContextHint] = useState(false);

  // ── Abort in-flight streams on unmount ───────────────────────────────────

  const bubbleRef = useRef<HTMLDivElement>(null);
  const preferenceWriter = useMemo(() => createPreferenceWriter({
    write: () => Promise.reject(new Error("Authentication unavailable")),
    onSaved: (saved) => {
      setPreferences(saved);
      setPreferenceSaveStatus((current) => ({ ...current, phase: "saved" }));
    },
    onFailure: () => setPreferenceSaveStatus((current) => ({ ...current, phase: "failed" })),
  }), [setPreferences]);

  useEffect(() => {
    if (preferenceSaveStatus.phase !== "pending" && preferenceSaveStatus.phase !== "saved") return;
    const delay = preferenceSaveStatus.phase === "pending" ? 350 : 1500;
    const timeout = setTimeout(() => {
      setPreferenceSaveStatus((current) => ({
        ...current,
        phase: current.phase === "pending" ? "saving" : current.phase === "saved" ? null : current.phase,
      }));
    }, delay);
    return () => clearTimeout(timeout);
  }, [preferenceSaveStatus.phase, preferenceSaveStatus.revision]);

  useEffect(() => {
    preferenceWriter.setWrite((value) => token
      ? updatePreferences(token, value)
      : Promise.reject(new Error("Authentication unavailable")));
    preferenceWriter.resume();
    return () => preferenceWriter.dispose();
  }, [preferenceWriter, token]);

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
    restoredGuestSearch,
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
  useAuthenticatedSearchRoute({
    experience,
    snapshot,
    restoreId,
    userId: isGuest ? null : userId,
    credential: isGuest ? null : token,
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSearchValue("");
    setVisibleCollections([]);
  }, [experience, searchKey]);

  // ── Search ────────────────────────────────────────────────────────────────

  const handleSearch = useCallback(
    async (queryOverride?: string) => {
      const query = queryOverride ?? searchValue;
      if (activeCollections.length === 0 || !query.trim()) return;
      setSearchValue("");
      setVisibleCollections([...activeCollections]);
      experience.send({
        type: "submit",
        request: {
          query,
          collections: activeCollections,
          translation,
          quota,
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

  // Save complete snapshots for deliberate selector changes, never for effect replay.
  // The writer confirms only its newest queued snapshot.
  function saveDefault(next: SearchDraft) {
    if (!next.preferences) return;
    if (isGuest) {
      saveGuestPreferenceDraft(next.preferences);
      return;
    }
    if (!token) return;
    setPreferenceSaveStatus((current) => ({ phase: "pending", revision: current.revision + 1 }));
    preferenceWriter.save(next.preferences);
  }

  function handleToggleCollection(c: string) {
    const next = transitionSearchDraft(draft, { type: "collection-toggled", collection: c });
    if (next === draft) return;
    trackCollectionToggled({
      collection: c,
      enabled: next.collections.includes(c),
      focusedEligible: next.focusedEligible,
      focusedSelected: next.quota === 10,
    });
    saveDefault(next);
    setDraft(next);
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
    if (q !== 3 && q !== 4 && q !== 5 && q !== 10) return;
    const next = transitionSearchDraft(draft, { type: "quota-selected", quota: q });
    if (next === draft) return;
    trackQuotaChanged({
      from: quota,
      to: next.quota,
      focusedEligible: next.focusedEligible,
      focusedSelected: next.quota === 10,
    });
    saveDefault(next);
    setDraft(next);
  }

  function handleTranslationChange(value: string) {
    const next = transitionSearchDraft(draft, { type: "translation-selected", translation: value });
    if (next === draft) return;
    saveDefault(next);
    setDraft(next);
  }

  function handleSelectQuery(text: string) {
    setSearchValue(text);
    handleSearch(text);
  }

  useLayoutEffect(() => {
    if (!searchView.showAnimation || !searchView.queryBubbleVisible
      || !searchView.submittedQuery) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBubbleSize(null);
      return;
    }
    const el = bubbleRef.current;
    if (!el) return;
    const { width, height } = el.getBoundingClientRect();
    if (width > 0 && height > 0) setBubbleSize({ width, height });
  }, [searchView.queryBubbleVisible, searchView.showAnimation, searchView.submittedQuery]);

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
            collections={searchView.submittedCollections.length > 0 ? [...searchView.submittedCollections] : [...activeCollections]}
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
        {searchView.queryBubbleVisible && searchView.submittedQuery && (
          <div
            ref={bubbleRef}
            className={`relative flex justify-end mb-4 ${searchView.showAnimation ? "z-20 pointer-events-none" : ""}`}
          >
            <div className="max-w-[70%] max-md:max-w-[85%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
              {searchView.submittedQuery}
            </div>
          </div>
        )}

        {!searchView.error && (searchView.loading || searchView.submittedQuery) && (
          <SearchResults
            results={[...searchView.passages]}
            loading={searchView.loading}
            searchId={searchView.searchId}
            token={token ?? ""}
            phase={searchView.phase}
            submittedCollections={[...searchView.submittedCollections]}
            visibleCollections={visibleCollections}
            outcome={searchView.outcome}
            collectionOutcomes={{ ...searchView.collectionOutcomes }}
            submittedQuota={searchView.submittedQuota}
            deliveryOutcome={searchView.deliveryOutcome}
            reportedResultCount={searchView.reportedResultCount}
            historicalOutcomeUnknown={searchView.historicalOutcomeUnknown}
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
            Some passages may be missing. Try the search again if you need a complete set.
          </div>
        )}

        {searchView.error && !searchView.loading && (
          <SearchFailureScreen
            code={searchView.errorCode}
            stage={searchView.errorStage}
            onRetry={() => {
              experience.send({ type: "retry" });
            }}
            onReport={isGuest ? undefined : () => {
              const safeCode = (["auth_error", "invalid_request", "network_error", "rate_limit", "restore_not_found", "restore_unavailable", "server_error", "stream_interrupted"] as const)
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
        onTranslationChange={handleTranslationChange}
        quota={searchView.loading && searchView.submittedQuota !== null ? searchView.submittedQuota : quota}
        onQuotaChange={handleQuotaChange}
        preferenceSaveStatus={isGuest ? null : preferenceSaveStatus.phase}
        searchValue={searchValue}
        onSearchChange={setSearchValue}
        onSearch={() => handleSearch(searchValue)}
        loading={searchView.loading}
        isSearchActive={searchView.showAnimation ? searchView.filterBarActive : searchView.submittedQuery !== null}
        submittedCollections={searchView.showAnimation ? [...searchView.submittedCollections] : filterBarCollections}
        visibleCollections={visibleCollections}
        onToggleVisible={handleToggleVisible}
        searchDisabled={false}
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
