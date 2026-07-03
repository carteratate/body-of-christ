"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { createClient } from "@/lib/supabase/client";
import { getPreferences, getSearchHistory, getSources, type Preferences, type SearchSummaryV2, type SourceDocument } from "@/lib/api";
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
}

const AppContext = createContext<AppContextValue>({
  token: null,
  ready: false,
  preferences: null,
  setPreferences: () => {},
  preferencesError: false,
  searches: [],
  refreshSearches: () => {},
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

  const setPendingSearch = useCallback((id: string, query: string) => {
    setPendingSearchState({ id, query });
  }, []);

  const clearPendingSearch = useCallback(() => {
    setPendingSearchState(null);
  }, []);

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getSession().then(({ data }) => {
      const t = data.session?.access_token ?? null;
      setToken(t);
      if (t) {
        getPreferences(t).then(setPreferences).catch(() => setPreferencesError(true));
        getSearchHistory(t).then(setSearches).catch(() => {});
        reloadSources(t);
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
    try { localStorage.setItem("boc-theme", theme); } catch (_) {}
  }, [preferences?.theme]);

  return (
    <AppContext.Provider value={{
      token, ready, preferences, setPreferences, preferencesError,
      searches, refreshSearches,
      pendingSearch, setPendingSearch, clearPendingSearch,
      activeSearchId, setActiveSearchId,
      searchKey, newSearch,
      sources, sourcesLoading, sourcesError, reloadSources,
      corpusPassages: sources.length > 0 ? sources.reduce((sum, s) => sum + s.chunk_count, 0) : null,
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
        <main className="flex flex-1 flex-col min-w-0">
          <MobileTopBar onOpenMenu={() => setMobileNavOpen(true)} />
          {ready ? children : null}
        </main>
      </div>
    </AppContext.Provider>
  );
}
