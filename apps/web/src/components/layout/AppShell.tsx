"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { getPreferences, type Preferences } from "@/lib/api";
import { Sidebar } from "./Sidebar";

// Preferences context — consumed by CollectionToggles, TranslationSelector, etc.
export interface AppContextValue {
  token: string | null;
  preferences: Preferences | null;
  setPreferences: (p: Preferences) => void;
  searchKey: number;
  newSearch: () => void;
}

const AppContext = createContext<AppContextValue>({
  token: null,
  preferences: null,
  setPreferences: () => {},
  searchKey: 0,
  newSearch: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [searchKey, setSearchKey] = useState(0);

  function newSearch() {
    router.push("/search");
    setSearchKey((k) => k + 1);
  }

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getSession().then(({ data }) => {
      const t = data.session?.access_token ?? null;
      setToken(t);
      if (t) {
        getPreferences(t).then(setPreferences).catch(() => {});
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_, session) => {
      const t = session?.access_token ?? null;
      setToken(t);
      if (!session) router.replace("/login");
    });

    return () => subscription.unsubscribe();
  }, [router]);

  return (
    <AppContext.Provider value={{ token, preferences, setPreferences, searchKey, newSearch }}>
      <div className="flex h-full bg-brand-bg text-brand-primary">
        <Sidebar token={token} />
        <main className="flex flex-1 flex-col min-w-0">
          {children}
        </main>
      </div>
    </AppContext.Provider>
  );
}
