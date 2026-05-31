"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAppContext } from "@/components/layout/AppShell";
import { ResultsSkeleton } from "@/components/search/ResultsSkeleton";
import { BookmarkCard } from "./BookmarkCard";
import { getBookmarks, type Bookmark } from "@/lib/api";

export function BookmarksPage() {
  const { token } = useAppContext();
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBookmarks = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    getBookmarks(token)
      .then((data) => {
        setBookmarks(data);
      })
      .catch(() => {
        setError("Couldn't load your saved passages. Please try again.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [token]);

  useEffect(() => {
    fetchBookmarks();
  }, [fetchBookmarks]);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-6 max-w-3xl w-full mx-auto">
        {/* Page heading */}
        <h1 className="text-2xl font-semibold text-brand-primary mb-6">Saved Passages</h1>

        {/* Loading state */}
        {loading && <ResultsSkeleton count={3} />}

        {/* Error state */}
        {!loading && error && (
          <div className="text-center py-12">
            <p className="text-brand-muted text-sm mb-4">{error}</p>
            <button
              onClick={fetchBookmarks}
              className="px-4 py-2 rounded text-sm text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              Retry
            </button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && bookmarks.length === 0 && (
          <div className="text-center py-16">
            <p className="text-brand-muted text-sm mb-4 max-w-sm mx-auto">
              You haven&apos;t saved any passages yet. Start exploring and save passages that speak to you.
            </p>
            <Link
              href="/search"
              className="inline-block px-4 py-2 rounded text-sm text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              Start Searching
            </Link>
          </div>
        )}

        {/* Results */}
        {!loading && !error && bookmarks.length > 0 && (
          <div className="space-y-3">
            {bookmarks.map((bookmark) => (
              <BookmarkCard
                key={bookmark.id}
                bookmark={bookmark}
                token={token}
                onRemoved={(id) => setBookmarks((prev) => prev.filter((b) => b.id !== id))}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
