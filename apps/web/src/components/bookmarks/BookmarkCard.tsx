"use client";

import { useRouter } from "next/navigation";
import { removeBookmark, type Bookmark } from "@/lib/api";
import { trackBookmarkDeleted, trackExploreMoreClicked } from "@/lib/analytics";
import { getCollectionMeta } from "@/lib/collections";

interface BookmarkCardProps {
  bookmark: Bookmark;
  token: string | null;
  onRemoved: (bookmarkId: string) => void;
  showToast: (message: string, type?: "success" | "error") => void;
}

export function BookmarkCard({ bookmark, token, onRemoved, showToast }: BookmarkCardProps) {
  const router = useRouter();

  // ── Null chunk fallback ───────────────────────────────────────────────────
  if (bookmark.chunk === null) {
    return (
      <div className="rounded-lg bg-brand-surface border-l-4 border-brand-surface p-4 flex items-center justify-between gap-3">
        <p className="text-sm text-brand-muted italic">Passage unavailable</p>
        <button
          onClick={() => {
            onRemoved(bookmark.id);
            if (token) removeBookmark(token, bookmark.id).catch(() => {});
          }}
          title="Remove bookmark"
          aria-label="Remove bookmark"
          className="p-1.5 rounded text-sm text-brand-accent transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          🔖
        </button>
      </div>
    );
  }

  const { content, source } = bookmark.chunk;
  const { collection, document_title, reference } = source;

  const collectionMeta = getCollectionMeta(collection);
  const borderColor = collectionMeta?.color ?? "var(--color-brand-accent)";
  const displayReference = reference ?? document_title;

  // ── Remove bookmark ───────────────────────────────────────────────────────
  async function handleRemove() {
    onRemoved(bookmark.id);
    if (token) {
      try {
        await removeBookmark(token, bookmark.id);
      } catch {
        showToast("Couldn't remove. Try again.", "error");
      }
    }
    trackBookmarkDeleted({ collection });
  }

  // ── Copy action ───────────────────────────────────────────────────────────
  function handleCopy() {
    const text = `${content} — ${displayReference} (${collection})`;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text)
        .then(() => showToast("Copied"))
        .catch(() => showToast("Copy failed", "error"));
    }
  }

  // ── Explore more action ───────────────────────────────────────────────────
  function handleExploreMore() {
    const trimmed = content.slice(0, 200).replace(/\s+\S*$/, "");
    trackExploreMoreClicked({ collection, source: "chunk_card" });
    router.push(`/search?explore=${encodeURIComponent(trimmed)}`);
  }

  return (
    <div
      className="rounded-lg bg-brand-surface border-l-4 p-4"
      style={{ borderLeftColor: borderColor }}
    >
      {/* Top row: badge + reference + action buttons */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {/* Collection badge */}
          <span
            className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border"
            style={{ borderColor: borderColor, color: borderColor }}
          >
            {collectionMeta?.label ?? collection}
          </span>
          {/* Reference */}
          <span className="text-sm text-brand-primary font-medium truncate">
            {displayReference}
          </span>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 shrink-0">
          {/* Remove bookmark */}
          <button
            onClick={handleRemove}
            title="Remove bookmark"
            aria-label="Remove bookmark"
            className="p-1.5 rounded text-sm transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            <span className="text-brand-accent">🔖</span>
          </button>

          {/* Copy */}
          <button
            onClick={handleCopy}
            title="Copy passage"
            aria-label="Copy passage"
            className="p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            📋
          </button>

          {/* Explore more */}
          <button
            onClick={handleExploreMore}
            title="Explore more like this"
            aria-label="Explore more like this"
            className="p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            🔍
          </button>
        </div>
      </div>

      {/* Content */}
      <p className="text-sm text-brand-primary leading-relaxed whitespace-pre-wrap">{content}</p>
    </div>
  );
}
