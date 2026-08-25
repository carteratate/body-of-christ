// apps/web/src/components/layout/GuestShell.tsx
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { AppContext, type AppContextValue } from "./AppShell";
import { Sidebar } from "./Sidebar";
import { MobileTopBar } from "./MobileTopBar";
import { GuestGateContext, type GuestGate } from "./guestGate";
import { GuestSignupModal } from "@/components/common";
import { useMobileNavigationDrawer } from "./useMobileNavigationDrawer";
import { getGuestSavedChunkIds, getGuestSearchCount, markGuestSearchCompleted, toggleGuestSavedChunk } from "@/lib/trial";

export function GuestShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [searchKey, setSearchKey] = useState(0);
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);
  const [pendingSearch, setPendingSearchState] = useState<{ id: string; query: string } | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [mobileNavTriggerId, setMobileNavTriggerId] = useState("mobile-nav-trigger");
  const [showSignup, setShowSignup] = useState(false);
  const [signupReason, setSignupReason] = useState<"limit" | "library" | "saved" | "history" | "notes" | "feature">("feature");
  const [searchCount, setSearchCount] = useState(0);
  const [savedChunkIds, setSavedChunkIds] = useState<string[]>([]);

  useEffect(() => {
    queueMicrotask(() => {
      setSearchCount(getGuestSearchCount());
      setSavedChunkIds(getGuestSavedChunkIds());
    });
  }, []);

  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);
  useMobileNavigationDrawer(mobileNavOpen, closeMobileNav, mobileNavTriggerId);
  const openMobileNavigation = useCallback((triggerId = "mobile-nav-trigger") => {
    setMobileNavTriggerId(triggerId);
    setMobileNavOpen(true);
  }, []);

  // Gated navigation opens a dismissible signup explanation. Also dismiss the
  // mobile drawer so the modal isn't stacked behind it.
  const requestSignup = useCallback((reason: "limit" | "library" | "saved" | "history" | "notes" | "feature" = "feature") => {
    setMobileNavOpen(false);
    setSignupReason(reason);
    setShowSignup(true);
  }, []);

  const recordCompletedSearch = useCallback(() => setSearchCount(markGuestSearchCompleted()), []);
  const toggleSaved = useCallback((chunkId: string) => {
    const isSaved = toggleGuestSavedChunk(chunkId);
    setSavedChunkIds(getGuestSavedChunkIds());
    return isSaved;
  }, []);
  const guestGate = useMemo<GuestGate>(() => ({
    requestSignup,
    searchCount,
    recordCompletedSearch,
    savedChunkIds,
    toggleSavedChunk: toggleSaved,
  }), [recordCompletedSearch, requestSignup, savedChunkIds, searchCount, toggleSaved]);

  const newSearch = useCallback(() => {
    setSearchKey((k) => k + 1);
    setActiveSearchId(null);
  }, []);

  const setPendingSearch = useCallback((id: string, query: string) => {
    setPendingSearchState({ id, query });
  }, []);

  const clearPendingSearch = useCallback((expectedId?: string) => {
    setPendingSearchState((current) => {
      if (expectedId && current?.id !== expectedId) return current;
      return null;
    });
  }, []);

  // Close nav on resize to desktop
  useEffect(() => {
    const mql = window.matchMedia("(min-width: 768px)");
    function handleChange(e: MediaQueryListEvent) {
      if (e.matches) setMobileNavOpen(false);
    }
    mql.addEventListener("change", handleChange);
    return () => mql.removeEventListener("change", handleChange);
  }, []);

  const value: AppContextValue = {
        token: null,
        userId: null,
    ready: true,
    preferences: null,
    setPreferences: () => {},
    preferencesError: false,
    searches: [],
    refreshSearches: () => {},
    removeSearch: () => {},
    restoreSearch: () => {},
    historyRevision: 0,
    invalidateSearchHistory: () => {},
    pendingSearch,
    setPendingSearch,
    clearPendingSearch,
    activeSearchId,
    setActiveSearchId,
    searchKey,
    newSearch,
    sources: [],
    sourcesLoading: false,
    sourcesReady: true,
    sourcesError: false,
    reloadSources: () => {},
    corpusPassages: null,
    bookmarkIds: {},
    setBookmarkForChunk: () => {},
    mobileNavigationOpen: mobileNavOpen,
    openMobileNavigation,
  };

  return (
    <AppContext.Provider value={value}>
      <GuestGateContext.Provider value={guestGate}>
        <div className="flex h-full bg-brand-bg text-brand-primary">
          <Sidebar isMobileOpen={mobileNavOpen} onCloseMobile={closeMobileNav} />
          {mobileNavOpen && (
            <div
              className="max-md:fixed max-md:inset-0 max-md:z-30 max-md:bg-black/50"
              onClick={closeMobileNav}
              aria-hidden="true"
            />
          )}
          <main inert={mobileNavOpen ? true : undefined} className="flex flex-1 min-h-0 min-w-0 flex-col overflow-hidden">
            {!pathname.startsWith("/reader/guest/") && (
              <MobileTopBar isOpen={mobileNavOpen} onOpenMenu={() => openMobileNavigation()} />
            )}
            {children}
          </main>
        </div>
        <GuestSignupModal isOpen={showSignup} reason={signupReason} onDismiss={() => setShowSignup(false)} />
      </GuestGateContext.Provider>
    </AppContext.Provider>
  );
}
