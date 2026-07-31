"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { createClient } from "@/lib/supabase/client";
import { getBookmarks, getPreferences, getSearchHistory, getSources, type Preferences, type SearchSummaryV2, type SourceDocument } from "@/lib/api";
import { MobileTopBar } from "./MobileTopBar";

const Sidebar = dynamic(
  () => import("./Sidebar").then((m) => ({ default: m.Sidebar })),
  { ssr: false }
);

export interface AppContextValue {
  token: string | null;
  ready: boolean;
  preferences: Preferences | null;
  setPreferences: (p: Preferences) => void;
  preferencesError: boolean;
  // Real DB-backed search history
  searches: SearchSummaryV2[];
  refreshSearches: () => void;
  removeSearch: (id: string) => void;
  // Separate pending slot — never conflicts with the DB list
  pendingSearch: { id: string; query: string } | null;
  setPendingSearch: (id: string, query: string) => void;
  clearPendingSearch: () => void;
  activeSearchId: string | null;
  setActiveSearchId: (id: string | null) => void;
  searchKey: number;
  newSearch: () => void;
  // Source corpus — fetched once on login, cached for the session
  sources: SourceDocument[];
  sourcesLoading: boolean;
  sourcesError: boolean;
  reloadSources: () => void;
  corpusPassages: number | null;
  bookmarkIds: Record<string, string>;
  setBookmarkForChunk: (chunkId: string, bookmarkId: string | null) => void;
}

export const AppContext = createContext<AppContextValue>({
  token: null,
  ready: false,
  preferences: null,
  setPreferences: () => {},
  preferencesError: false,
  searches: [],
  refreshSearches: () => {},
  removeSearch: () => {},
  pendingSearch: null,
  setPendingSearch: () => {},
  clearPendingSearch: () => {},
  activeSearchId: null,
  setActiveSearchId: () => {},
  searchKey: 0,
  newSearch: () => {},
  sources: [],
  sourcesLoading: false,
  sourcesError: false,
  reloadSources: () => {},
  corpusPassages: null,
  bookmarkIds: {},
  setBookmarkForChunk: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [preferencesError, setPreferencesError] = useState(false);
  const [searches, setSearches] = useState<SearchSummaryV2[]>([]);
  const [pendingSearch, setPendingSearchState] = useState<{ id: string; query: string } | null>(null);
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);
  const [searchKey, setSearchKey] = useState(0);
  const [ready, setReady] = useState(false);
  const [sources, setSources] = useState<SourceDocument[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [bookmarkIds, setBookmarkIds] = useState<Record<string, string>>({});

  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);

  function newSearch() {
    setSearchKey((k) => k + 1);
    setActiveSearchId(null);
  }

  const reloadSources = useCallback((tok?: string) => {
    const t = tok ?? token;
    if (!t) return;
    setSourcesLoading(true);
    setSourcesError(false);
    getSources(t)
      .then(setSources)
      .catch(() => setSourcesError(true))
      .finally(() => setSourcesLoading(false));
  }, [token]);

  const refreshSearches = useCallback(() => {
    if (!token) return;
    // Only updates the real DB list — pendingSearch is managed separately
    getSearchHistory(token).then(setSearches).catch(() => {});
  }, [token]);

  const removeSearch = useCallback((id: string) => {
    setSearches((prev) => prev.filter((s) => s.id !== id));
  }, []);

  const setPendingSearch = useCallback((id: string, query: string) => {
    setPendingSearchState({ id, query });
  }, []);

  const clearPendingSearch = useCallback(() => {
    setPendingSearchState(null);
  }, []);

  const setBookmarkForChunk = useCallback((chunkId: string, bookmarkId: string | null) => {
    setBookmarkIds((prev) => {
      if (bookmarkId) return { ...prev, [chunkId]: bookmarkId };
      const next = { ...prev };
      delete next[chunkId];
      return next;
    });
  }, []);

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getSession().then(({ data }) => {
      const t = data.session?.access_token ?? null;
      setToken(t);
      if (t) {
        const critical = Promise.allSettled([
          getPreferences(t).then(setPreferences).catch(() => setPreferencesError(true)),
          getSearchHistory(t).then(setSearches).catch(() => {}),
        ]);
        critical.finally(() => {
          const warmCaches = () => {
            setSourcesLoading(true);
            getSources(t)
              .then(setSources)
              .catch(() => setSourcesError(true))
              .finally(() => setSourcesLoading(false));
            getBookmarks(t)
              .then((items) => setBookmarkIds(Object.fromEntries(items.map((b) => [b.chunk_id, b.id]))))
              .catch(() => {});
          };
          if ("requestIdleCallback" in window) {
            window.requestIdleCallback(warmCaches, { timeout: 1500 });
          } else {
            setTimeout(warmCaches, 0);
          }
        });
      }
      setReady(true);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_, session) => {
      const t = session?.access_token ?? null;
      setToken(t);
      if (!session) {
        window.location.replace("/login");
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    const theme = preferences?.theme;
    if (!theme) return;
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theocorpus-theme", theme); } catch {}
  }, [preferences?.theme]);

  useEffect(() => {
    if (!mobileNavOpen) return;

    document.body.style.overflow = "hidden";
    const drawer = document.getElementById("mobile-nav-drawer");

    const focusables = drawer?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])');
    focusables?.[0]?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setMobileNavOpen(false);
        return;
      }
      if (e.key !== "Tab" || !drawer) return;
      const items = Array.from(drawer.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", handleKeyDown);
      document.getElementById("mobile-nav-trigger")?.focus();
    };
  }, [mobileNavOpen]);

  useEffect(() => {
    const mql = window.matchMedia("(min-width: 768px)");
    function handleChange(e: MediaQueryListEvent) {
      if (e.matches) setMobileNavOpen(false);
    }
    mql.addEventListener("change", handleChange);
    return () => mql.removeEventListener("change", handleChange);
  }, []);

  return (
    <AppContext.Provider value={{
      token, ready, preferences, setPreferences, preferencesError,
      searches, refreshSearches, removeSearch,
      pendingSearch, setPendingSearch, clearPendingSearch,
      activeSearchId, setActiveSearchId,
      searchKey, newSearch,
      sources, sourcesLoading, sourcesError, reloadSources,
      corpusPassages: sources.length > 0 ? sources.reduce((sum, s) => sum + s.chunk_count, 0) : null,
      bookmarkIds, setBookmarkForChunk,
    }}>
      <div className="flex h-full bg-brand-bg text-brand-primary">
        <Sidebar isMobileOpen={mobileNavOpen} onCloseMobile={closeMobileNav} />
        {mobileNavOpen && (
          <div
            className="max-md:fixed max-md:inset-0 max-md:z-30 max-md:bg-black/50"
            onClick={closeMobileNav}
            aria-hidden="true"
          />
        )}
        <main className="flex flex-1 min-h-0 min-w-0 flex-col overflow-hidden">
          <MobileTopBar isOpen={mobileNavOpen} onOpenMenu={() => setMobileNavOpen(true)} />
          {ready ? children : null}
        </main>
      </div>
    </AppContext.Provider>
  );
}
