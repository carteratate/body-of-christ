"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { useAppContext } from "@/components/layout/AppShell";
import { SavedPassagesSkeleton } from "@/components/common/PageSkeletons";
import { BookmarkCard } from "./BookmarkCard";
import { getBookmarks, removeBookmark, type Bookmark } from "@/lib/api";
import { Toast, useToast } from "@/components/common";
import { getCollectionMeta } from "@/lib/collections";

function normalizeSearchValue(value: string | null | undefined): string {
  return (value ?? "")
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .trim()
    .toLowerCase();
}

function compareBookmarksNewest(first: Bookmark, second: Bookmark): number {
  const timestampDifference = Date.parse(second.created_at) - Date.parse(first.created_at);
  return timestampDifference || second.id.localeCompare(first.id);
}

export function BookmarksPage() {
  const { token, setBookmarkForChunk } = useAppContext();
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const requestRef = useRef(0);
  const { toast, showToast, dismissToast } = useToast();

  function fetchBookmarks() {
    if (!token) return;
    const requestId = ++requestRef.current;
    setLoading(true);
    setError(null);
    getBookmarks(token, true)
      .then((data) => {
        if (requestId !== requestRef.current) return;
        setBookmarks(data);
      })
      .catch(() => {
        if (requestId !== requestRef.current) return;
        setError("Couldn't load your saved passages. Please try again.");
      })
      .finally(() => {
        if (requestId === requestRef.current) setLoading(false);
      });
  }

  useEffect(() => {
    setQuery("");
    if (!token) {
      setBookmarks([]);
      setLoading(false);
      return;
    }
    fetchBookmarks();
    return () => {
      requestRef.current += 1;
    };
  // fetchBookmarks intentionally uses the token captured for this effect.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const filteredBookmarks = useMemo(() => {
    const term = normalizeSearchValue(query);
    if (!term) return bookmarks;
    return bookmarks.filter((bookmark) => {
      const source = bookmark.chunk?.source;
      const collectionLabel = source ? getCollectionMeta(source.collection)?.label : null;
      return [
        bookmark.note,
        bookmark.chunk?.content,
        source?.reference,
        source?.document_title,
        source?.author,
        source?.collection,
        collectionLabel,
      ].some((value) => normalizeSearchValue(value).includes(term));
    });
  }, [bookmarks, query]);

  function handleNoteUpdated(bookmarkId: string, note: string | null) {
    setBookmarks((prev) =>
      prev.map((b) => (b.id === bookmarkId ? { ...b, note } : b))
    );
  }

  async function handleRemove(bookmark: Bookmark) {
    if (!token) return;
    const mutationRequestId = requestRef.current;
    setBookmarks((prev) => prev.filter((b) => b.id !== bookmark.id));
    setBookmarkForChunk(bookmark.chunk_id, null);
    try {
      await removeBookmark(token, bookmark.id);
    } catch {
      if (mutationRequestId !== requestRef.current) return;
      setBookmarks((prev) => {
        if (prev.some((item) => item.id === bookmark.id)) return prev;
        return [...prev, bookmark].sort(compareBookmarksNewest);
      });
      setBookmarkForChunk(bookmark.chunk_id, bookmark.id);
      showToast("Couldn't remove passage. Restored.", "error");
    }
  }

  if (loading) return <SavedPassagesSkeleton />;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="mx-auto w-full min-w-0 max-w-3xl px-4 py-5 sm:px-6 sm:py-6">
        <h1 className="mb-5 text-2xl font-semibold text-brand-primary">Saved Passages</h1>

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

        {!loading && !error && bookmarks.length > 0 && (
          <label className="mb-5 flex min-w-0 items-center gap-2 rounded-md border border-brand-muted/30 bg-brand-surface px-3 focus-within:border-brand-accent">
            <Search size={17} className="shrink-0 text-brand-muted" aria-hidden="true" />
            <span className="sr-only">Search saved passages</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search passages, sources, or notes"
              className="min-w-0 flex-1 bg-transparent py-3 text-brand-primary outline-none placeholder:text-brand-muted"
            />
          </label>
        )}

        {!loading && !error && bookmarks.length > 0 && filteredBookmarks.length === 0 && (
          <div className="py-12 text-center">
            <p className="text-sm text-brand-muted">No saved passages match that search.</p>
            <button type="button" onClick={() => setQuery("")} className="mt-3 text-sm text-brand-accent hover:underline">Clear search</button>
          </div>
        )}

        {!loading && !error && bookmarks.length > 0 && (
          <div className="space-y-3">
            {filteredBookmarks.map((bookmark) => (
              <BookmarkCard
                key={bookmark.id}
                bookmark={bookmark}
                token={token}
                onRemove={handleRemove}
                onNoteUpdated={handleNoteUpdated}
                showToast={showToast}
              />
            ))}
          </div>
        )}
      </div>
      {toast.visible && <Toast message={toast.message} type={toast.type} onDismiss={dismissToast} />}
    </div>
  );
}
