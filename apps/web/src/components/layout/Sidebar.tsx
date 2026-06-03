"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { getSearchHistory, type SearchSummaryV2 } from "@/lib/api";

interface SidebarProps {
  token: string | null;
}

export function Sidebar({ token }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [searches, setSearches] = useState<SearchSummaryV2[]>([]);

  useEffect(() => {
    if (!token) return;
    getSearchHistory(token).then(setSearches).catch(() => {});
  }, [token]);

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <aside className="flex flex-col w-56 shrink-0 bg-brand-surface border-r border-brand-surface h-full">
      {/* App name */}
      <div className="px-4 pt-5 pb-3 border-b border-brand-bg">
        <span className="text-brand-accent font-semibold text-sm tracking-wide">Body of Christ</span>
      </div>

      {/* New search button */}
      <div className="px-3 pt-3">
        <a
          href="/search"
          className="block w-full text-center bg-brand-accent text-brand-bg rounded-md py-1.5 text-sm font-semibold hover:opacity-90 transition-opacity"
        >
          + New Search
        </a>
      </div>

      {/* Recent searches */}
      <div className="flex-1 overflow-y-auto px-3 pt-3 space-y-1">
        <p className="text-brand-muted text-[10px] uppercase tracking-widest font-medium px-1 mb-2">
          Recent
        </p>
        {searches.length === 0 && (
          <p className="text-brand-muted text-xs px-1">No recent searches.</p>
        )}
        {searches.map((s) => (
          <Link
            key={s.id}
            href={`/search?restore=${s.id}`}
            className={`block px-2 py-1.5 rounded text-xs truncate transition-colors ${
              pathname.includes(s.id)
                ? "bg-brand-bg text-brand-accent border-l-2 border-brand-accent"
                : "text-brand-muted hover:bg-brand-bg hover:text-brand-primary"
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
          href="/bookmarks"
          className={`block px-2 py-1.5 rounded transition-colors ${
            pathname === "/bookmarks"
              ? "text-brand-accent"
              : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          🔖 Saved Passages
        </Link>
        <button
          onClick={handleSignOut}
          className="block w-full text-left px-2 py-1.5 rounded text-brand-muted hover:text-brand-primary transition-colors"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
