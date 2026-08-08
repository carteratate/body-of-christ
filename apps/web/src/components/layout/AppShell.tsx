"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { getBookmarks, getPreferences, getSearchHistory, getSources, type Preferences, type SearchSummaryV2, type SourceDocument } from "@/lib/api";
import { clearFeedbackContext } from "@/lib/feedbackContext";
import { MobileTopBar } from "./MobileTopBar";
import { useMobileNavigationDrawer } from "./useMobileNavigationDrawer";

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
  restoreSearch: (search: SearchSummaryV2, index: number) => void;
  historyRevision: number;
  invalidateSearchHistory: () => void;
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
  openMobileNavigation: (triggerId?: string) => void;
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
  restoreSearch: () => {},
  historyRevision: 0,
  invalidateSearchHistory: () => {},
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
  openMobileNavigation: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [token, setToken] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [preferencesError, setPreferencesError] = useState(false);
  const [searches, setSearches] = useState<SearchSummaryV2[]>([]);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [pendingSearch, setPendingSearchState] = useState<{ id: string; query: string } | null>(null);
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);
  const [searchKey, setSearchKey] = useState(0);
  const [ready, setReady] = useState(false);
  const [sources, setSources] = useState<SourceDocument[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [mobileNavTriggerId, setMobileNavTriggerId] = useState("mobile-nav-trigger");
  const [bookmarkIds, setBookmarkIds] = useState<Record<string, string>>({});
  const searchHistoryRequestGeneration = useRef(0);
  const userResourceGeneration = useRef(0);
  const authUserIdRef = useRef<string | null>(null);

  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);
  useMobileNavigationDrawer(mobileNavOpen, closeMobileNav, mobileNavTriggerId);

  const openMobileNavigation = useCallback((triggerId = "mobile-nav-trigger") => {
    setMobileNavTriggerId(triggerId);
    setMobileNavOpen(true);
  }, []);

  function newSearch() {
    setSearchKey((k) => k + 1);
    setActiveSearchId(null);
  }

  const reloadSources = useCallback((tok?: string) => {
    const t = tok ?? token;
    if (!t) return;
    const generation = userResourceGeneration.current;
    setSourcesLoading(true);
    setSourcesError(false);
    getSources(t)
      .then((items) => { if (generation === userResourceGeneration.current) setSources(items); })
      .catch(() => { if (generation === userResourceGeneration.current) setSourcesError(true); })
      .finally(() => { if (generation === userResourceGeneration.current) setSourcesLoading(false); });
  }, [token]);

  const loadSearchHistory = useCallback(async (requestToken: string) => {
    const generation = ++searchHistoryRequestGeneration.current;
    try {
      const history = await getSearchHistory(requestToken);
      if (generation === searchHistoryRequestGeneration.current) setSearches(history);
    } catch {
      // History is non-critical; retain the last known local state.
    }
  }, []);

  const refreshSearches = useCallback(() => {
    if (token) void loadSearchHistory(token);
  }, [loadSearchHistory, token]);

  const removeSearch = useCallback((id: string) => {
    searchHistoryRequestGeneration.current += 1;
    setSearches((prev) => prev.filter((s) => s.id !== id));
  }, []);

  const restoreSearch = useCallback((search: SearchSummaryV2, index: number) => {
    searchHistoryRequestGeneration.current += 1;
    setSearches((prev) => {
      if (prev.some((item) => item.id === search.id)) return prev;
      const next = [...prev];
      next.splice(Math.min(index, next.length), 0, search);
      return next;
    });
  }, []);

  const invalidateSearchHistory = useCallback(() => {
    setHistoryRevision((revision) => revision + 1);
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
      authUserIdRef.current = data.session?.user.id ?? null;
      const t = data.session?.access_token ?? null;
      setToken(t);
      if (t) {
        const generation = userResourceGeneration.current;
        const critical = Promise.allSettled([
          getPreferences(t)
            .then((value) => { if (generation === userResourceGeneration.current) setPreferences(value); })
            .catch(() => { if (generation === userResourceGeneration.current) setPreferencesError(true); }),
          loadSearchHistory(t),
        ]);
        critical.finally(() => {
          if (generation !== userResourceGeneration.current) return;
          const warmCaches = () => {
            if (generation !== userResourceGeneration.current) return;
            setSourcesLoading(true);
            getSources(t)
              .then((items) => { if (generation === userResourceGeneration.current) setSources(items); })
              .catch(() => { if (generation === userResourceGeneration.current) setSourcesError(true); })
              .finally(() => { if (generation === userResourceGeneration.current) setSourcesLoading(false); });
            getBookmarks(t)
              .then((items) => {
                if (generation === userResourceGeneration.current) {
                  setBookmarkIds(Object.fromEntries(items.map((b) => [b.chunk_id, b.id])));
                }
              })
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
      const nextUserId = session?.user.id ?? null;
      if (authUserIdRef.current !== null && authUserIdRef.current !== nextUserId) {
        clearFeedbackContext();
        userResourceGeneration.current += 1;
        searchHistoryRequestGeneration.current += 1;
        setToken(null);
        setPreferences(null);
        setPreferencesError(false);
        setSearches([]);
        setPendingSearchState(null);
        setActiveSearchId(null);
        setSources([]);
        setSourcesLoading(false);
        setSourcesError(false);
        setBookmarkIds({});
        authUserIdRef.current = nextUserId;
        window.location.replace(nextUserId ? "/search" : "/login");
        return;
      }
      authUserIdRef.current = nextUserId;
      const t = session?.access_token ?? null;
      setToken(t);
      if (!session) {
        clearFeedbackContext();
        window.location.replace("/login");
      }
    });

    return () => subscription.unsubscribe();
  }, [loadSearchHistory]);

  useEffect(() => {
    const theme = preferences?.theme;
    if (!theme) return;
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theocorpus-theme", theme); } catch {}
  }, [preferences?.theme]);

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
      searches, refreshSearches, removeSearch, restoreSearch,
      historyRevision, invalidateSearchHistory,
      pendingSearch, setPendingSearch, clearPendingSearch,
      activeSearchId, setActiveSearchId,
      searchKey, newSearch,
      sources, sourcesLoading, sourcesError, reloadSources,
      corpusPassages: sources.length > 0 ? sources.reduce((sum, s) => sum + s.chunk_count, 0) : null,
      bookmarkIds, setBookmarkForChunk,
      openMobileNavigation,
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
        <main inert={mobileNavOpen ? true : undefined} className="flex flex-1 min-h-0 min-w-0 flex-col overflow-hidden">
          {!pathname.startsWith("/reader/") && (
            <MobileTopBar isOpen={mobileNavOpen} onOpenMenu={() => openMobileNavigation()} />
          )}
          {ready ? children : null}
        </main>
      </div>
    </AppContext.Provider>
  );
}
