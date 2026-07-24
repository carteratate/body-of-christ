"use client";

import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAppContext } from "./AppShell";
import { useGuestGate } from "./guestGate";
import { Library, Bookmark, Church, Settings, BarChart3, X } from "lucide-react";
import { deleteSearch } from "@/lib/api";
import { Toast, useToast } from "@/components/common";

interface SidebarProps {
  isMobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ isMobileOpen, onCloseMobile }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { newSearch, searches, pendingSearch, activeSearchId, token, removeSearch, refreshSearches } =
    useAppContext();
  const guestGate = useGuestGate();
  const { toast, showToast, dismissToast } = useToast();

  function handleNewSearch() {
    // Guest funnel: New Search prompts signup instead of starting another search.
    if (guestGate) {
      guestGate.requestSignup();
      return;
    }
    router.push("/search");
    newSearch();
    onCloseMobile();
  }

  // Guest funnel: nav links lead to gated areas, so they prompt signup instead.
  function handleNavClick(e: React.MouseEvent) {
    if (guestGate) {
      e.preventDefault();
      guestGate.requestSignup();
      return;
    }
    onCloseMobile();
  }

  async function handleDeleteSearch(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    if (!token) return;
    removeSearch(id);
    if (id === activeSearchId) {
      router.push("/search");
      newSearch();
    }
    try {
      await deleteSearch(token, id);
    } catch {
      refreshSearches();
      showToast("Couldn't delete search. Restored.", "error");
    }
  }

  const activeClass = "bg-brand-bg text-brand-accent border-l-2 border-brand-accent";
  const inactiveClass = "text-brand-muted hover:bg-brand-bg hover:text-brand-primary";

  return (
    <>
    <aside
      id="mobile-nav-drawer"
      className={`flex flex-col w-56 shrink-0 bg-brand-surface border-r border-brand-surface h-full max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:w-72 max-md:transition-transform max-md:duration-200 ${
        isMobileOpen ? "max-md:translate-x-0" : "max-md:-translate-x-full"
      }`}
    >
      {/* App name */}
      <div className="px-4 pt-3 pb-2 border-b border-brand-bg">
        <span className="text-brand-accent font-semibold text-2xl whitespace-nowrap font-brand">TheoCorpus</span>
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
          <div
            key={s.id}
            className={`group flex items-center rounded transition-colors ${
              s.id === activeSearchId ? activeClass : inactiveClass
            }`}
          >
            <Link
              href={`/search?restore=${s.id}`}
              onClick={handleNavClick}
              className="block flex-1 min-w-0 px-2 py-1.5 text-xs truncate"
              title={s.query}
            >
              {s.query}
            </Link>
            <button
              type="button"
              onClick={(e) => handleDeleteSearch(e, s.id)}
              aria-label="Delete search"
              className="shrink-0 px-1.5 py-1.5 rounded text-brand-muted hover:text-brand-danger opacity-0 group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-60 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              <X size={12} />
            </button>
          </div>
        ))}
      </div>

      {/* Bottom nav */}
      <div className="px-3 pb-4 pt-2 border-t border-brand-bg space-y-1 text-xs">
        <Link
          href="/sources"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/sources" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Library size={12} /> List of Sources
        </Link>
        <Link
          href="/discover"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/discover" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <BarChart3 size={12} /> Custom Source Scores
        </Link>
        <Link
          href="/bookmarks"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/bookmarks" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Bookmark size={12} /> Saved Passages
        </Link>
        <Link
          href="/about"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/about" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Church size={12} /> About
        </Link>
        <Link
          href="/settings"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/settings" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Settings size={12} /> Settings
        </Link>
      </div>
    </aside>

    {toast.visible && <Toast message={toast.message} type={toast.type} onDismiss={dismissToast} />}
    </>
  );
}
