"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { createClient } from "@/lib/supabase/client";
import { getPreferences, getSearchHistory, type Preferences, type SearchSummaryV2 } from "@/lib/api";

const Sidebar = dynamic(
  () => import("./Sidebar").then((m) => ({ default: m.Sidebar })),
  { ssr: false }
);

export interface AppContextValue {
  token: string | null;
  ready: boolean;
  preferences: Preferences | null;
  setPreferences: (p: Preferences) => void;
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
}

const AppContext = createContext<AppContextValue>({
  token: null,
  ready: false,
  preferences: null,
  setPreferences: () => {},
  searches: [],
  refreshSearches: () => {},
  pendingSearch: null,
  setPendingSearch: () => {},
  clearPendingSearch: () => {},
  activeSearchId: null,
  setActiveSearchId: () => {},
  searchKey: 0,
  newSearch: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [searches, setSearches] = useState<SearchSummaryV2[]>([]);
  const [pendingSearch, setPendingSearchState] = useState<{ id: string; query: string } | null>(null);
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);
  const [searchKey, setSearchKey] = useState(0);
  const [ready, setReady] = useState(false);

  function newSearch() {
    setSearchKey((k) => k + 1);
    setActiveSearchId(null);
  }

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
        getPreferences(t).then(setPreferences).catch(() => {});
        getSearchHistory(t).then(setSearches).catch(() => {});
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

  return (
    <AppContext.Provider value={{
      token, ready, preferences, setPreferences,
      searches, refreshSearches,
      pendingSearch, setPendingSearch, clearPendingSearch,
      activeSearchId, setActiveSearchId,
      searchKey, newSearch,
    }}>
      <div className="flex h-full bg-brand-bg text-brand-primary">
        <Sidebar />
        <main className="flex flex-1 flex-col min-w-0">
          {ready ? children : null}
        </main>
      </div>
    </AppContext.Provider>
  );
}
