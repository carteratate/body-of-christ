"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { claimGuestSession, getBookmarks, getPreferences, getSearchHistory, getSources, GuestClaimHttpError, type Preferences, type SearchSummaryV2, type SourceDocument } from "@/lib/api";
import { clearGuestSession, getGuestSavedChunkIds, peekGuestSessionToken } from "@/lib/trial";
import { clearFeedbackContext } from "@/lib/feedbackContext";
import { MobileTopBar } from "./MobileTopBar";
import { useMobileNavigationDrawer } from "./useMobileNavigationDrawer";
import { PageErrorState, PageLoadingState } from "@/components/common/PageStates";

const Sidebar = dynamic(
  () => import("./Sidebar").then((m) => ({ default: m.Sidebar })),
  { ssr: false }
);

export interface AppContextValue {
  token: string | null;
  userId: string | null;
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
  clearPendingSearch: (expectedId?: string) => void;
  activeSearchId: string | null;
  setActiveSearchId: (id: string | null) => void;
  searchKey: number;
  newSearch: () => void;
  // Source corpus — fetched once on login, cached for the session
  sources: SourceDocument[];
  sourcesLoading: boolean;
  sourcesReady: boolean;
  sourcesError: boolean;
  reloadSources: () => void;
  corpusPassages: number | null;
  bookmarkIds: Record<string, string>;
  setBookmarkForChunk: (chunkId: string, bookmarkId: string | null) => void;
  mobileNavigationOpen: boolean;
  openMobileNavigation: (triggerId?: string) => void;
}

export const AppContext = createContext<AppContextValue>({
  token: null,
  userId: null,
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
  sourcesReady: false,
  sourcesError: false,
  reloadSources: () => {},
  corpusPassages: null,
  bookmarkIds: {},
  setBookmarkForChunk: () => {},
  mobileNavigationOpen: false,
  openMobileNavigation: () => {},
});

export function useAppContext() {
  return useContext(AppContext);
}

async function getSessionWithTimeout(
  client: ReturnType<typeof createClient>,
  timeoutMs = 5000,
) {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      client.auth.getSession(),
      new Promise<never>((_, reject) => {
        timeoutId = setTimeout(() => reject(new Error("Session check timed out")), timeoutMs);
      }),
    ]);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [token, setToken] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [preferencesError, setPreferencesError] = useState(false);
  const [searches, setSearches] = useState<SearchSummaryV2[]>([]);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [pendingSearch, setPendingSearchState] = useState<{ id: string; query: string } | null>(null);
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);
  const [searchKey, setSearchKey] = useState(0);
  const [ready, setReady] = useState(false);
  const [authResolutionError, setAuthResolutionError] = useState(false);
  const [sources, setSources] = useState<SourceDocument[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesReady, setSourcesReady] = useState(false);
  const [sourcesError, setSourcesError] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [mobileNavTriggerId, setMobileNavTriggerId] = useState("mobile-nav-trigger");
  const [bookmarkIds, setBookmarkIds] = useState<Record<string, string>>({});
  const [guestTransferStatus, setGuestTransferStatus] = useState<"idle" | "transferring" | "failed" | "auth-required" | "auth-renewal-failed" | "ownership-conflict">("idle");
  const guestTransferPromiseRef = useRef<Promise<boolean> | null>(null);
  const guestTransferAbortRef = useRef<AbortController | null>(null);
  const searchHistoryRequestGeneration = useRef(0);
  const userResourceGeneration = useRef(0);
  const sourcesRequestGeneration = useRef(0);
  const authUserIdRef = useRef<string | null>(null);
  const authRecoveryTargetRef = useRef<string | null>(null);

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
    const requestGeneration = ++sourcesRequestGeneration.current;
    setSourcesLoading(true);
    setSourcesReady(false);
    setSourcesError(false);
    getSources(t)
      .then((items) => {
        if (generation === userResourceGeneration.current && requestGeneration === sourcesRequestGeneration.current) setSources(items);
      })
      .catch(() => {
        if (generation === userResourceGeneration.current && requestGeneration === sourcesRequestGeneration.current) setSourcesError(true);
      })
      .finally(() => {
        if (generation === userResourceGeneration.current && requestGeneration === sourcesRequestGeneration.current) {
          setSourcesLoading(false);
          setSourcesReady(true);
        }
      });
  }, [token]);
  const pathnameAtMountRef = useRef(pathname);
  const reloadSourcesRef = useRef(reloadSources);

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

  const clearPendingSearch = useCallback((expectedId?: string) => {
    setPendingSearchState((current) => {
      if (expectedId && current?.id !== expectedId) return current;
      return null;
    });
  }, []);

  const setBookmarkForChunk = useCallback((chunkId: string, bookmarkId: string | null) => {
    setBookmarkIds((prev) => {
      if (bookmarkId) return { ...prev, [chunkId]: bookmarkId };
      const next = { ...prev };
      delete next[chunkId];
      return next;
    });
  }, []);

  const transferGuestActivity = useCallback((accessToken: string): Promise<boolean> => {
    const guestToken = peekGuestSessionToken();
    if (!guestToken) {
      setGuestTransferStatus("idle");
      return Promise.resolve(true);
    }
    if (guestTransferPromiseRef.current) return guestTransferPromiseRef.current;
    const transferController = new AbortController();
    const initiatingGeneration = userResourceGeneration.current;
    const initiatingUserId = authUserIdRef.current;
    guestTransferAbortRef.current = transferController;
    const transfer = (async () => {
      setGuestTransferStatus("transferring");
      const delays = [0, 1000, 3000];
      let claimAccessToken = accessToken;
      let refreshedTokenRetried = false;
      let skipDelay = false;
      const stillOwnsTransfer = () => (
        !transferController.signal.aborted
        && initiatingGeneration === userResourceGeneration.current
        && initiatingUserId === authUserIdRef.current
      );
      for (let attempt = 0; attempt < delays.length; attempt += 1) {
        if (!skipDelay && delays[attempt] > 0) {
          const delayCompleted = await new Promise<boolean>((resolve) => {
            const timer = window.setTimeout(() => {
              transferController.signal.removeEventListener("abort", cancelDelay);
              resolve(true);
            }, delays[attempt]);
            const cancelDelay = () => {
              window.clearTimeout(timer);
              resolve(false);
            };
            transferController.signal.addEventListener("abort", cancelDelay, { once: true });
          });
          if (!delayCompleted || !stillOwnsTransfer()) return false;
        }
        skipDelay = false;
        const claimController = new AbortController();
        const cancelClaim = () => claimController.abort();
        transferController.signal.addEventListener("abort", cancelClaim, { once: true });
        const claimTimeout = window.setTimeout(() => claimController.abort(), 5000);
        try {
          await claimGuestSession(
            claimAccessToken,
            guestToken,
            getGuestSavedChunkIds(),
            claimController.signal,
          );
          if (!stillOwnsTransfer()) return false;
          clearGuestSession();
          setGuestTransferStatus("idle");
          return true;
        } catch (error) {
          if (!stillOwnsTransfer()) return false;
          // A 409 means the final streamed explanations are still being persisted;
          // transient network/5xx failures use the same bounded background retry.
          if (error instanceof GuestClaimHttpError) {
            if (error.status === 401 || error.status === 403) {
              let latestAccessToken: string | null;
              try {
                const { data, error: sessionError } = await getSessionWithTimeout(createClient());
                if (sessionError) throw sessionError;
                if (data.session?.user.id !== initiatingUserId) {
                  transferController.abort();
                  return false;
                }
                latestAccessToken = data.session?.access_token ?? null;
              } catch {
                if (stillOwnsTransfer()) setGuestTransferStatus("failed");
                return false;
              }
              if (!stillOwnsTransfer()) return false;
              if (
                !refreshedTokenRetried
                && latestAccessToken
                && latestAccessToken !== claimAccessToken
              ) {
                // A request begun just before Supabase refreshed the session may
                // legitimately reject the old token. Retry the claim once with the
                // replacement token before treating the session as expired.
                refreshedTokenRetried = true;
                claimAccessToken = latestAccessToken;
                attempt -= 1;
                skipDelay = true;
                continue;
              }

              // Do not sign out a newer session that arrived after the rejected
              // claim. Its next mount/manual retry can safely resume the transfer.
              let confirmedAccessToken: string | null;
              try {
                const { data: confirmed, error: sessionError } = await getSessionWithTimeout(createClient());
                if (sessionError) throw sessionError;
                if (confirmed.session?.user.id !== initiatingUserId) {
                  transferController.abort();
                  return false;
                }
                confirmedAccessToken = confirmed.session?.access_token ?? null;
              } catch {
                if (stillOwnsTransfer()) setGuestTransferStatus("failed");
                return false;
              }
              if (!stillOwnsTransfer()) return false;
              if (confirmedAccessToken && confirmedAccessToken !== claimAccessToken) {
                setGuestTransferStatus("failed");
                return false;
              }

              // A claim failure must never automatically destroy a session that
              // Supabase could refresh immediately after this check. Preserve the
              // guest activity and let the user explicitly renew authentication.
              setGuestTransferStatus("auth-required");
              return false;
            }
            const retryable = (
              (error.status === 409 && error.message === "Guest search is still completing")
              || error.status === 429
              || error.status >= 500
            );
            if (!retryable) {
              setGuestTransferStatus(
                error.status === 409
                  && error.message === "This trial activity was already transferred to another account."
                  ? "ownership-conflict"
                  : "failed",
              );
              return false;
            }
          }
        } finally {
          window.clearTimeout(claimTimeout);
          transferController.signal.removeEventListener("abort", cancelClaim);
        }
      }
      if (stillOwnsTransfer()) setGuestTransferStatus("failed");
      return false;
    })();
    guestTransferPromiseRef.current = transfer;
    void transfer.finally(() => {
      if (guestTransferPromiseRef.current === transfer) guestTransferPromiseRef.current = null;
      if (guestTransferAbortRef.current === transferController) guestTransferAbortRef.current = null;
    });
    return transfer;
  }, []);

  useEffect(() => {
    const supabase = createClient();

    getSessionWithTimeout(supabase).then(({ data, error }) => {
      if (error) throw error;
      const initialUserId = data.session?.user.id ?? null;
      authUserIdRef.current = initialUserId;
      setUserId(initialUserId);
      const t = data.session?.access_token ?? null;
      setToken(t);
      if (t) {
        setAuthResolutionError(false);
        const generation = userResourceGeneration.current;
        const transfer = transferGuestActivity(t);
        let effectiveToken = t;
        const critical = transfer.then(async () => {
          const { data: current, error: sessionError } = await getSessionWithTimeout(supabase);
          if (sessionError) throw sessionError;
          const currentToken = current.session?.access_token ?? null;
          if (!currentToken) throw new Error("Authenticated session is no longer available");
          effectiveToken = currentToken;
          setToken(currentToken);
          if (pathnameAtMountRef.current === "/sources") reloadSourcesRef.current(currentToken);
          await Promise.allSettled([
            getPreferences(currentToken)
              .then((value) => { if (generation === userResourceGeneration.current) setPreferences(value); })
              .catch(() => { if (generation === userResourceGeneration.current) setPreferencesError(true); }),
            loadSearchHistory(currentToken),
          ]);
        }).catch(() => {
          if (generation === userResourceGeneration.current) setAuthResolutionError(true);
        });
        critical.finally(() => {
          if (generation !== userResourceGeneration.current) return;
          const warmCaches = () => {
            if (generation !== userResourceGeneration.current) return;
            if (pathnameAtMountRef.current !== "/sources") reloadSourcesRef.current(effectiveToken);
            getBookmarks(effectiveToken)
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
          // Keep transfer-dependent pages behind the destination loading state
          // until guest history and saved passages have either been claimed or
          // the user has been given the visible retry state.
          setReady(true);
        });
      } else {
        window.location.replace("/login");
      }
    }).catch(() => {
      setAuthResolutionError(true);
      setReady(true);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      const nextUserId = session?.user.id ?? null;
      if (authUserIdRef.current !== null && authUserIdRef.current !== nextUserId) {
        guestTransferAbortRef.current?.abort();
        guestTransferPromiseRef.current = null;
        clearFeedbackContext();
        userResourceGeneration.current += 1;
        searchHistoryRequestGeneration.current += 1;
        setToken(null);
        setUserId(null);
        setPreferences(null);
        setPreferencesError(false);
        setSearches([]);
        setPendingSearchState(null);
        setActiveSearchId(null);
        setSources([]);
        setSourcesLoading(false);
        setSourcesReady(false);
        setSourcesError(false);
        setBookmarkIds({});
        authUserIdRef.current = nextUserId;
        const recoveryTarget = authRecoveryTargetRef.current;
        authRecoveryTargetRef.current = null;
        window.location.replace(nextUserId ? "/search" : recoveryTarget ?? "/login");
        return;
      }
      authUserIdRef.current = nextUserId;
      setUserId(nextUserId);
      const t = session?.access_token ?? null;
      setToken(t);
      if (event === "SIGNED_OUT" || !session) {
        clearFeedbackContext();
        const recoveryTarget = authRecoveryTargetRef.current ?? "/login";
        authRecoveryTargetRef.current = null;
        window.location.replace(recoveryTarget);
      }
    });

    return () => {
      guestTransferAbortRef.current?.abort();
      guestTransferPromiseRef.current = null;
      subscription.unsubscribe();
    };
  }, [loadSearchHistory, transferGuestActivity]);

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
      token, userId, ready, preferences, setPreferences, preferencesError,
      searches, refreshSearches, removeSearch, restoreSearch,
      historyRevision, invalidateSearchHistory,
      pendingSearch, setPendingSearch, clearPendingSearch,
      activeSearchId, setActiveSearchId,
      searchKey, newSearch,
      sources, sourcesLoading, sourcesReady, sourcesError, reloadSources,
      corpusPassages: sources.length > 0 ? sources.reduce((sum, s) => sum + s.chunk_count, 0) : null,
      bookmarkIds, setBookmarkForChunk,
      mobileNavigationOpen: mobileNavOpen,
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
          {guestTransferStatus !== "idle" && (
            <div role="status" className={`flex items-center justify-center gap-3 border-b px-4 py-2 text-sm ${guestTransferStatus !== "transferring" ? "border-brand-danger/30 bg-brand-danger/10 text-brand-primary" : "border-brand-accent/30 bg-brand-accent/10 text-brand-muted"}`}>
              <span>
                {guestTransferStatus === "auth-renewal-failed"
                  ? "We couldn't reopen sign-in. Your trial activity is still safe in this browser."
                  : guestTransferStatus === "ownership-conflict"
                    ? "This trial activity was already added to another account. Sign in with that account to view it; the browser copy has not been deleted."
                  : guestTransferStatus === "auth-required"
                  ? "Your session needs to be renewed before your trial activity can transfer. It is still safe in this browser."
                  : guestTransferStatus === "failed"
                  ? "Your trial activity has not transferred yet. It is still safe in this browser."
                  : "Adding your trial searches and saved passages to your account…"}
              </span>
              {guestTransferStatus === "failed" && token && (
                <button
                  type="button"
                  onClick={() => {
                    void transferGuestActivity(token).then((transferred) => {
                      if (!transferred) return;
                      // The History and Saved Passages screens own their displayed
                      // lists. Reload the current destination after a manual retry
                      // so those screens fetch the newly transferred records too.
                      window.location.reload();
                    });
                  }}
                  className="shrink-0 font-semibold text-brand-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
                >
                  Retry transfer
                </button>
              )}
              {(guestTransferStatus === "auth-required" || guestTransferStatus === "auth-renewal-failed") && (
                <button
                  type="button"
                  onClick={() => {
                    authRecoveryTargetRef.current = "/login?reason=session-expired";
                    void createClient().auth.signOut({ scope: "local" })
                      .then(({ error }) => {
                        if (error) {
                          authRecoveryTargetRef.current = null;
                          setGuestTransferStatus("auth-renewal-failed");
                          return;
                        }
                        window.location.replace("/login?reason=session-expired");
                      })
                      .catch(() => {
                        authRecoveryTargetRef.current = null;
                        setGuestTransferStatus("auth-renewal-failed");
                      });
                  }}
                  className="shrink-0 font-semibold text-brand-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
                >
                  Sign in again
                </button>
              )}
              {guestTransferStatus === "ownership-conflict" && (
                <button
                  type="button"
                  onClick={() => {
                    authRecoveryTargetRef.current = "/login?reason=trial-other-account";
                    void createClient().auth.signOut({ scope: "local" })
                      .then(({ error }) => {
                        if (error) {
                          authRecoveryTargetRef.current = null;
                          setGuestTransferStatus("auth-renewal-failed");
                          return;
                        }
                        window.location.replace("/login?reason=trial-other-account");
                      })
                      .catch(() => {
                        authRecoveryTargetRef.current = null;
                        setGuestTransferStatus("auth-renewal-failed");
                      });
                  }}
                  className="shrink-0 font-semibold text-brand-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
                >
                  Switch account
                </button>
              )}
            </div>
          )}
          {!ready ? (
            <PageLoadingState />
          ) : authResolutionError ? (
            <PageErrorState reset={() => window.location.reload()} />
          ) : (
            children
          )}
        </main>
      </div>
    </AppContext.Provider>
  );
}
