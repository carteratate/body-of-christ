"use client";

import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAppContext } from "./AppShell";
import { Library, Bookmark, Church, Settings, BarChart3 } from "lucide-react";

export function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { newSearch, searches, pendingSearch, activeSearchId } = useAppContext();

  function handleNewSearch() {
    router.push("/search");
    newSearch();
  }

  const activeClass = "bg-brand-bg text-brand-accent border-l-2 border-brand-accent";
  const inactiveClass = "text-brand-muted hover:bg-brand-bg hover:text-brand-primary";

  return (
    <aside className="flex flex-col w-56 shrink-0 bg-brand-surface border-r border-brand-surface h-full">
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
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/sources" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Library size={12} /> List of Sources
        </Link>
        <Link
          href="/discover"
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/discover" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <BarChart3 size={12} /> Custom Source Scores
        </Link>
        <Link
          href="/bookmarks"
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/bookmarks" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Bookmark size={12} /> Saved Passages
        </Link>
        <Link
          href="/about"
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/about" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Church size={12} /> About
        </Link>
        <Link
          href="/settings"
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
