// apps/web/src/components/layout/GuestShell.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { AppContext, type AppContextValue } from "./AppShell";
import { MobileTopBar } from "./MobileTopBar";

const Sidebar = dynamic(
  () => import("./Sidebar").then((m) => ({ default: m.Sidebar })),
  { ssr: false }
);

export function GuestShell({ children }: { children: React.ReactNode }) {
  const [searchKey, setSearchKey] = useState(0);
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);
  const [pendingSearch, setPendingSearchState] = useState<{ id: string; query: string } | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);

  const newSearch = useCallback(() => {
    setSearchKey((k) => k + 1);
    setActiveSearchId(null);
  }, []);

  const setPendingSearch = useCallback((id: string, query: string) => {
    setPendingSearchState({ id, query });
  }, []);

  const clearPendingSearch = useCallback(() => setPendingSearchState(null), []);

  // Close nav on resize to desktop
  useEffect(() => {
    const mql = window.matchMedia("(min-width: 768px)");
    function handleChange(e: MediaQueryListEvent) {
      if (e.matches) setMobileNavOpen(false);
    }
    mql.addEventListener("change", handleChange);
    return () => mql.removeEventListener("change", handleChange);
  }, []);

  // Mobile nav focus trap + scroll lock (mirrors AppShell)
  useEffect(() => {
    if (!mobileNavOpen) return;
    document.body.style.overflow = "hidden";
    const drawer = document.getElementById("mobile-nav-drawer");
    const focusables = drawer?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])');
    focusables?.[0]?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") { setMobileNavOpen(false); return; }
      if (e.key !== "Tab" || !drawer) return;
      const items = Array.from(drawer.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'));
      if (items.length === 0) return;
      const first = items[0]; const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", handleKeyDown);
      document.getElementById("mobile-nav-trigger")?.focus();
    };
  }, [mobileNavOpen]);

  const value: AppContextValue = {
    token: null,
    ready: true,
    preferences: null,
    setPreferences: () => {},
    preferencesError: false,
    searches: [],
    refreshSearches: () => {},
    pendingSearch,
    setPendingSearch,
    clearPendingSearch,
    activeSearchId,
    setActiveSearchId,
    searchKey,
    newSearch,
    sources: [],
    sourcesLoading: false,
    sourcesError: false,
    reloadSources: () => {},
    corpusPassages: null,
    bookmarkIds: {},
    setBookmarkForChunk: () => {},
  };

  return (
    <AppContext.Provider value={value}>
      <div className="flex h-full bg-brand-bg text-brand-primary">
        <Sidebar isMobileOpen={mobileNavOpen} onCloseMobile={closeMobileNav} />
        {mobileNavOpen && (
          <div
            className="max-md:fixed max-md:inset-0 max-md:z-30 max-md:bg-black/50"
            onClick={closeMobileNav}
            aria-hidden="true"
          />
        )}
        <main className="flex flex-1 flex-col min-w-0">
          <MobileTopBar isOpen={mobileNavOpen} onOpenMenu={() => setMobileNavOpen(true)} />
          {children}
        </main>
      </div>
    </AppContext.Provider>
  );
}
