# Mobile-Responsive Nav Shell + Search Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Body of Christ web app usable on phone-width viewports (<768px) — a collapsible off-canvas nav drawer replacing the always-visible sidebar, plus targeted Search-page layout fixes — while keeping ≥768px rendering pixel-identical to today.

**Architecture:** The existing `Sidebar` component becomes responsive via Tailwind `max-md:` variants layered onto its current classes (no existing class removed), driven by a `mobileNavOpen` boolean held in `AppShell`. A new `MobileTopBar` component (hamburger + wordmark) renders only below the breakpoint and toggles that state. Three small Search-page components get isolated `max-md:` layout tweaks for existing overflow/squeeze risks identified during design review.

**Tech Stack:** Next.js (App Router) + React + TypeScript, Tailwind CSS v4 (`max-*` variants), lucide-react icons. No frontend test runner exists in this repo (confirmed: no Jest/Vitest/RTL, no `*.test.*` files, no test script in `apps/web/package.json`) — verification is `npm run lint`, `npm run build` (which type-checks via `tsc` during the Next build), and manual browser verification at named viewport sizes, per this repo's existing convention for UI work.

## Global Constraints

- Every mobile-specific change to an **existing** file must use `max-md:` Tailwind variants only — no unprefixed (desktop-governing) class is removed or edited. (Spec: "Governing technical principle")
- Breakpoint pivot is Tailwind's `md` (768px), consistently, across every task in this plan.
- `AppContextValue` (exported from `AppShell.tsx`) gains **no new fields** — `mobileNavOpen` stays local state passed via props to `Sidebar`/`MobileTopBar` only. (Spec: "Non-goals")
- Desktop/laptop (≥768px) must remain pixel-identical to current `master` at the end of every task that touches a shared component (`Sidebar`, `AppShell`).
- Files touched across this entire plan: `apps/web/src/components/layout/AppShell.tsx`, `apps/web/src/components/layout/Sidebar.tsx`, `apps/web/src/components/layout/MobileTopBar.tsx` (new), `apps/web/src/components/search/BottomBar.tsx`, `apps/web/src/components/search/ChunkCard.tsx`, `apps/web/src/components/search/SearchPage.tsx`. No other file may be modified — Reader, Bookmarks, Sources, Discover, Settings, and About are out of scope (Phase 2 spec).

---

### Task 1: Responsive nav shell — core drawer behavior

**Files:**
- Create: `apps/web/src/components/layout/MobileTopBar.tsx`
- Modify: `apps/web/src/components/layout/Sidebar.tsx` (full file — every nav/history `Link` and the "New Search" button needs an added close-callback, plus the `<aside>` needs new responsive classes and two new props)
- Modify: `apps/web/src/components/layout/AppShell.tsx` (full file — new state, new imports, new render output)

**Interfaces:**
- Produces: `Sidebar` now requires two props: `isMobileOpen: boolean`, `onCloseMobile: () => void`. Any code rendering `<Sidebar />` must pass both.
- Produces: `MobileTopBar` component with props `{ onOpenMenu: () => void }`, rendered inside `<main>`, hidden at `md:` and above.
- Produces (AppShell-local, not exported): `mobileNavOpen: boolean` state and `closeMobileNav: () => void` — consumed by Task 2 in this same file.

- [ ] **Step 1: Create `MobileTopBar.tsx`**

```tsx
"use client";

import { Menu } from "lucide-react";

interface MobileTopBarProps {
  onOpenMenu: () => void;
}

export function MobileTopBar({ onOpenMenu }: MobileTopBarProps) {
  return (
    <div className="flex md:hidden items-center gap-3 h-[52px] shrink-0 px-3 border-b border-brand-surface bg-brand-surface">
      <button
        onClick={onOpenMenu}
        aria-label="Open menu"
        className="p-2 -ml-1 rounded text-brand-primary hover:bg-brand-bg transition-colors"
      >
        <Menu size={20} />
      </button>
      <span className="text-brand-accent font-semibold text-lg font-brand">Body of Christ</span>
    </div>
  );
}
```

This is a brand-new component (no existing desktop behavior to preserve), so it uses the standard Tailwind `md:hidden` idiom directly rather than `max-md:` — there's nothing to clash with.

- [ ] **Step 2: Replace `Sidebar.tsx` in full**

```tsx
"use client";

import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAppContext } from "./AppShell";
import { Library, Bookmark, Church, Settings, BarChart3 } from "lucide-react";

interface SidebarProps {
  isMobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ isMobileOpen, onCloseMobile }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { newSearch, searches, pendingSearch, activeSearchId } = useAppContext();

  function handleNewSearch() {
    router.push("/search");
    newSearch();
    onCloseMobile();
  }

  const activeClass = "bg-brand-bg text-brand-accent border-l-2 border-brand-accent";
  const inactiveClass = "text-brand-muted hover:bg-brand-bg hover:text-brand-primary";

  return (
    <aside
      className={`flex flex-col w-56 shrink-0 bg-brand-surface border-r border-brand-surface h-full max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:w-72 max-md:transition-transform max-md:duration-200 ${
        isMobileOpen ? "max-md:translate-x-0" : "max-md:-translate-x-full"
      }`}
    >
      {/* App name */}
      <div className="px-4 pt-3 pb-2 border-b border-brand-bg">
        <span className="text-brand-accent font-semibold text-2xl whitespace-nowrap font-brand">Body of Christ</span>
      </div>

      {/* New search button */}
      <div className="px-3 pt-2">
        <button
          onClick={handleNewSearch}
          className="block w-full text-center bg-brand-accent text-brand-bg rounded-md py-1.5 text-base font-semibold hover:opacity-90 transition-opacity whitespace-nowrap font-brand"
        >
          + New Search
        </button>
      </div>

      {/* Recent searches */}
      <div className="flex-1 overflow-y-auto px-3 pt-3 space-y-1">
        <p className="text-brand-muted text-[10px] uppercase tracking-widest font-medium px-1 mb-2">
          Recent
        </p>

        {/* Pending slot — shown only during a fresh/active search, never navigable */}
        {pendingSearch && (
          <div
            className={`block px-2 py-1.5 rounded text-xs truncate ${
              pendingSearch.id === activeSearchId ? activeClass : inactiveClass
            }`}
            title={pendingSearch.query}
          >
            {pendingSearch.query}
          </div>
        )}

        {/* Real DB-backed searches */}
        {searches.length === 0 && !pendingSearch && (
          <p className="text-brand-muted text-xs px-1">No recent searches.</p>
        )}
        {searches.map((s) => (
          <Link
            key={s.id}
            href={`/search?restore=${s.id}`}
            onClick={onCloseMobile}
            className={`block px-2 py-1.5 rounded text-xs truncate transition-colors ${
              s.id === activeSearchId ? activeClass : inactiveClass
            }`}
            title={s.query}
          >
            {s.query}
          </Link>
        ))}
      </div>

      {/* Bottom nav */}
      <div className="px-3 pb-4 pt-2 border-t border-brand-bg space-y-1 text-xs">
        <Link
          href="/sources"
          onClick={onCloseMobile}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/sources" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Library size={12} /> List of Sources
        </Link>
        <Link
          href="/discover"
          onClick={onCloseMobile}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/discover" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <BarChart3 size={12} /> Custom Source Scores
        </Link>
        <Link
          href="/bookmarks"
          onClick={onCloseMobile}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/bookmarks" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Bookmark size={12} /> Saved Passages
        </Link>
        <Link
          href="/about"
          onClick={onCloseMobile}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/about" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Church size={12} /> About
        </Link>
        <Link
          href="/settings"
          onClick={onCloseMobile}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/settings" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Settings size={12} /> Settings
        </Link>
      </div>
    </aside>
  );
}
```

- [ ] **Step 3: Replace `AppShell.tsx` in full**

```tsx
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
```

- [ ] **Step 4: Run lint**

Run: `cd apps/web && npm run lint`
Expected: no errors (warnings pre-existing elsewhere are fine; nothing new from these three files).

- [ ] **Step 5: Manual verification — desktop parity**

Run: `cd apps/web && npm run dev`, open `http://localhost:3000/search` logged in, browser at ≥1024px width (no device toolbar).
Expected: Sidebar renders exactly as before — static left column, always visible, no hamburger/top bar visible anywhere. This must look identical to `master` before this change.

- [ ] **Step 6: Manual verification — mobile drawer**

In browser dev tools, open the device toolbar and set viewport to 375×667.
Expected:
- A ~52px top bar appears with a hamburger icon and "Body of Christ" wordmark; the old sidebar is not visible.
- Clicking the hamburger slides the sidebar in from the left over the content, with a dimmed backdrop behind it.
- Clicking the backdrop closes the drawer.
- Opening the drawer again, clicking a history entry or a nav link (e.g. "Saved Passages") both navigates to that page **and** closes the drawer automatically.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/components/layout/MobileTopBar.tsx apps/web/src/components/layout/Sidebar.tsx apps/web/src/components/layout/AppShell.tsx
git commit -m "feat(mobile): add collapsible off-canvas nav drawer for phone widths"
```

---

### Task 2: Nav shell — accessibility & edge-case refinements

**Files:**
- Modify: `apps/web/src/components/layout/Sidebar.tsx` (add one `id` attribute to the `<aside>`)
- Modify: `apps/web/src/components/layout/MobileTopBar.tsx` (add `isOpen` prop, `id` + `aria-expanded` on the button)
- Modify: `apps/web/src/components/layout/AppShell.tsx` (add two `useEffect` hooks: focus-trap/Escape/scroll-lock, and matchMedia auto-close)

**Interfaces:**
- Consumes: `mobileNavOpen` / `setMobileNavOpen` from Task 1 (already in scope in `AppShell.tsx`).
- Produces: `MobileTopBar` props become `{ isOpen: boolean; onOpenMenu: () => void }` — the existing call site in `AppShell.tsx` from Task 1 must be updated to pass `isOpen={mobileNavOpen}`.

- [ ] **Step 1: Add an `id` to the Sidebar's `<aside>`**

In `apps/web/src/components/layout/Sidebar.tsx`, change:

```tsx
    <aside
      className={`flex flex-col w-56 shrink-0 bg-brand-surface border-r border-brand-surface h-full max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:w-72 max-md:transition-transform max-md:duration-200 ${
        isMobileOpen ? "max-md:translate-x-0" : "max-md:-translate-x-full"
      }`}
    >
```

to:

```tsx
    <aside
      id="mobile-nav-drawer"
      className={`flex flex-col w-56 shrink-0 bg-brand-surface border-r border-brand-surface h-full max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:w-72 max-md:transition-transform max-md:duration-200 ${
        isMobileOpen ? "max-md:translate-x-0" : "max-md:-translate-x-full"
      }`}
    >
```

- [ ] **Step 2: Add `isOpen`, `id`, and `aria-expanded` to `MobileTopBar`**

Replace the full contents of `apps/web/src/components/layout/MobileTopBar.tsx`:

```tsx
"use client";

import { Menu } from "lucide-react";

interface MobileTopBarProps {
  isOpen: boolean;
  onOpenMenu: () => void;
}

export function MobileTopBar({ isOpen, onOpenMenu }: MobileTopBarProps) {
  return (
    <div className="flex md:hidden items-center gap-3 h-[52px] shrink-0 px-3 border-b border-brand-surface bg-brand-surface">
      <button
        id="mobile-nav-trigger"
        onClick={onOpenMenu}
        aria-label="Open menu"
        aria-expanded={isOpen}
        aria-controls="mobile-nav-drawer"
        className="p-2 -ml-1 rounded text-brand-primary hover:bg-brand-bg transition-colors"
      >
        <Menu size={20} />
      </button>
      <span className="text-brand-accent font-semibold text-lg font-brand">Body of Christ</span>
    </div>
  );
}
```

- [ ] **Step 3: Update the `MobileTopBar` call site and add the two effects in `AppShell.tsx`**

In `apps/web/src/components/layout/AppShell.tsx`, change the render call:

```tsx
          <MobileTopBar onOpenMenu={() => setMobileNavOpen(true)} />
```

to:

```tsx
          <MobileTopBar isOpen={mobileNavOpen} onOpenMenu={() => setMobileNavOpen(true)} />
```

And add these two effects directly below the existing `useEffect(() => { const theme = ... }, [preferences?.theme]);` block (same file, same component body):

```tsx
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
```

- [ ] **Step 4: Run lint**

Run: `cd apps/web && npm run lint`
Expected: no errors.

- [ ] **Step 5: Manual verification**

At 375×667 viewport:
- Open the drawer. Press Tab repeatedly — focus should cycle only through the drawer's links/buttons and never reach content behind the backdrop. Press Shift+Tab from the first item — focus wraps to the last item.
- Press Escape — drawer closes, and a visible focus ring returns to the hamburger button.
- With the drawer open, try to scroll the page behind it (mouse wheel or touch drag on the dimmed area) — background must not scroll.
- Open the drawer, then resize the viewport to 1024px width without closing it — drawer should auto-close (no lingering open state if you later shrink back below 768px).
At 1024px (desktop), confirm no visible change at all — no hamburger, no top bar, sidebar static.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/layout/Sidebar.tsx apps/web/src/components/layout/MobileTopBar.tsx apps/web/src/components/layout/AppShell.tsx
git commit -m "feat(mobile): add focus trap, escape-to-close, scroll lock, and resize auto-close to nav drawer"
```

---

### Task 3: Search — BottomBar mobile stacking

**Files:**
- Modify: `apps/web/src/components/search/BottomBar.tsx:57`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 (independent).
- Produces: nothing consumed by later tasks (independent).

- [ ] **Step 1: Add stacking classes to the pre-search control row**

In `apps/web/src/components/search/BottomBar.tsx`, change:

```tsx
      <div className="mb-2 flex items-center justify-between gap-3">
```

to:

```tsx
      <div className="mb-2 flex items-center justify-between gap-3 max-md:flex-col max-md:items-stretch max-md:gap-2">
```

- [ ] **Step 2: Run lint**

Run: `cd apps/web && npm run lint`
Expected: no errors.

- [ ] **Step 3: Manual verification**

At 375×667, open `/search` before running a search. Expected: the collection-toggle pills row renders above the "Per source: 3/4/5" quota control, each spanning the full width, no horizontal squeeze or overlap.
At 1024px, confirm the row renders exactly as before — collection pills and quota control side by side, `justify-between`.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/search/BottomBar.tsx
git commit -m "fix(mobile): stack collection toggles and quota control on phone widths"
```

---

### Task 4: Search — ChunkCard mobile adjustments

**Files:**
- Modify: `apps/web/src/components/search/ChunkCard.tsx:178` (relevance label), `:236` (action row wrapper), `:287-293` ("Query more sources like this" button)

**Interfaces:**
- Consumes: nothing from other tasks (independent).
- Produces: nothing consumed by later tasks (independent).

- [ ] **Step 1: Hide the "Relevance Score:" text label on mobile**

Change:

```tsx
              <span className="text-brand-primary" style={{ fontSize: "11px" }}>Relevance Score:</span>
```

to:

```tsx
              <span className="text-brand-primary max-md:hidden" style={{ fontSize: "11px" }}>Relevance Score:</span>
```

- [ ] **Step 2: Allow the expanded action row to wrap on mobile**

Change:

```tsx
          <div className="flex items-center justify-between mt-3 gap-2">
```

to:

```tsx
          <div className="flex items-center justify-between mt-3 gap-2 max-md:flex-wrap">
```

- [ ] **Step 3: Shorten the "Query more sources like this" label on mobile**

Change:

```tsx
              <button
                onClick={handleExploreMore}
                aria-label="Query more sources like this"
                className="px-2 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
              >
                Query more sources like this
              </button>
```

to:

```tsx
              <button
                onClick={handleExploreMore}
                aria-label="Query more sources like this"
                className="px-2 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
              >
                <span className="max-md:hidden">Query more sources like this</span>
                <span className="hidden max-md:inline">Explore more</span>
              </button>
```

- [ ] **Step 4: Run lint**

Run: `cd apps/web && npm run lint`
Expected: no errors.

- [ ] **Step 5: Manual verification**

At 375×667, run a search, expand a result card that has a relevance score. Expected: header shows only the percentage chip (no "Relevance Score:" text); the action row wraps onto a second line without clipping any button; the rightmost button reads "Explore more".
At 1024px, confirm: full "Relevance Score:" label visible, single-row action bar, button reads the full "Query more sources like this" — identical to current `master`.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/search/ChunkCard.tsx
git commit -m "fix(mobile): prevent chunk-card header and action row overflow on phone widths"
```

---

### Task 5: Search — query bubble mobile width

**Files:**
- Modify: `apps/web/src/components/search/SearchPage.tsx:430` (in-animation bubble), `:443` (post-animation bubble)

**Interfaces:**
- Consumes: nothing from other tasks (independent).
- Produces: nothing consumed by later tasks (independent).

- [ ] **Step 1: Widen the max width on both query-bubble instances**

Change:

```tsx
          <div className="absolute top-4 right-4 z-20 max-w-[70%] pointer-events-none">
```

to:

```tsx
          <div className="absolute top-4 right-4 z-20 max-w-[70%] max-md:max-w-[85%] pointer-events-none">
```

And change:

```tsx
            <div className="max-w-[70%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
```

to:

```tsx
            <div className="max-w-[70%] max-md:max-w-[85%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
```

- [ ] **Step 2: Run lint**

Run: `cd apps/web && npm run lint`
Expected: no errors.

- [ ] **Step 3: Manual verification**

At 375×667, submit a long query (e.g. "what does the church teach about the nature of the trinity and its relationship to salvation"). Expected: the query bubble spans up to ~85% of the viewport width instead of wrapping tightly at 70%.
At 1024px, confirm the bubble's max width is unchanged (still capped at 70%).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/search/SearchPage.tsx
git commit -m "fix(mobile): widen query bubble max-width on phone viewports"
```

---

### Task 6: Cross-breakpoint verification pass

**Files:** none expected (verification only — fix-and-commit only if a real issue is found).

**Interfaces:**
- Consumes: the fully merged output of Tasks 1–5.

- [ ] **Step 1: Full production build**

Run: `cd apps/web && npm run build`
Expected: build succeeds with no TypeScript or lint errors across all files touched in Tasks 1–5.

- [ ] **Step 2: Desktop/laptop parity check**

Run: `cd apps/web && npm run dev`. At 1024×768 and 1440×900, open `/search` and `/bookmarks`.
Expected: both pages render identically to how they rendered before this plan started — no hamburger, no top bar, sidebar static and always visible, no layout shift in `BottomBar`, `ChunkCard`, or the query bubble.

- [ ] **Step 3: Phone-width integration check**

At 375×667 and 390×844, on `/search`:
- Confirm the nav drawer opens/closes via hamburger, backdrop click, and Escape, and auto-closes on link/history selection.
- Perform a real search with at least 2 collections selected. Confirm the collection-toggle/quota row stacks correctly, results render, and expanding a chunk card shows the mobile-adjusted header and wrapped action row together (integration check — Tasks 3 and 4 were verified in isolation; confirm they don't conflict when combined on the same page).
- Confirm the query bubble renders at the wider mobile max-width.

- [ ] **Step 4: Tablet boundary check**

At exactly 768×1024 (the `md` breakpoint itself), confirm the page renders in **desktop** mode (Tailwind's `md:` is `min-width: 768px`, so 768px exactly should show the static sidebar, not the drawer).

- [ ] **Step 5: Fix any issues found, or confirm clean**

If Steps 2–4 surfaced a real defect, fix it in the relevant file (following the `max-md:`-only constraint from Global Constraints) and re-run the affected check. If everything passed, no code changes are needed for this task.

- [ ] **Step 6: Commit (only if fixes were made)**

```bash
git add -A
git commit -m "fix(mobile): address issues found in cross-breakpoint verification pass"
```
