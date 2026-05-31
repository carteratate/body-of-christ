"use client";

import { useState } from "react";
import { addBookmark, removeBookmark, type ReaderChunk as ReaderChunkType, type DocumentInfo } from "@/lib/api";
import {
  trackBookmarkCreated,
  trackBookmarkDeleted,
  trackExploreMoreClicked,
} from "@/lib/analytics";
import { getCollectionMeta } from "@/lib/collections";

interface ReaderChunkProps {
  chunk: ReaderChunkType;
  document: DocumentInfo;
  isOrigin: boolean;
  token: string;
  onExploreMore: (content: string) => void;
}

export function ReaderChunk({ chunk, document, isOrigin, token, onExploreMore }: ReaderChunkProps) {
  const collectionMeta = getCollectionMeta(document.collection);
  const borderColor = isOrigin
    ? "var(--color-brand-accent)"
    : (collectionMeta?.color ?? "var(--color-brand-accent)");

  // ── Bookmark state ─────────────────────────────────────────────────────────
  const [isBookmarked, setIsBookmarked] = useState(false);
  const [bookmarkId, setBookmarkId] = useState<string | null>(null);

  async function handleBookmark() {
    if (!token) return;
    try {
      if (isBookmarked && bookmarkId) {
        await removeBookmark(token, bookmarkId);
        setIsBookmarked(false);
        setBookmarkId(null);
        trackBookmarkDeleted({ collection: document.collection });
      } else {
        const result = await addBookmark(token, chunk.id);
        setBookmarkId(result.id);
        setIsBookmarked(true);
        trackBookmarkCreated({ collection: document.collection, rankPositionWhenSaved: chunk.position });
      }
    } catch {
      // silent failure — non-critical
    }
  }

  // ── Copy action ────────────────────────────────────────────────────────────
  function handleCopy() {
    const text = `${chunk.content} — ${chunk.reference ?? document.title} (${document.collection})`;
    navigator.clipboard.writeText(text).catch(() => {});
  }

  // ── Explore more action ────────────────────────────────────────────────────
  function handleExploreMore() {
    const trimmed = chunk.content.slice(0, 200).replace(/\s+\S*$/, "");
    trackExploreMoreClicked({ collection: document.collection, source: "reader" });
    onExploreMore(trimmed);
  }

  return (
    <div
      className="rounded-lg bg-brand-surface border-l-4 p-4 mb-3"
      style={{ borderLeftColor: borderColor }}
    >
      {/* Origin label */}
      {isOrigin && (
        <p className="text-brand-accent text-xs mb-1">← Your result</p>
      )}

      {/* Reference label */}
      {chunk.reference && (
        <p className="text-brand-muted text-xs mb-1">{chunk.reference}</p>
      )}

      {/* Top-right actions */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1" />
        <div className="flex items-center gap-1 shrink-0">
          {/* Bookmark */}
          <button
            onClick={handleBookmark}
            title={isBookmarked ? "Remove bookmark" : "Save passage"}
            aria-label={isBookmarked ? "Remove bookmark" : "Save passage"}
            className="p-1.5 rounded text-sm transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            <span className={isBookmarked ? "text-brand-accent" : "text-brand-muted"}>🔖</span>
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
            aria-label="Explore more like this"
            className="px-2 py-1 rounded text-xs text-brand-muted border border-brand-surface hover:text-brand-primary hover:border-brand-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            🔍 Explore more
          </button>
        </div>
      </div>

      {/* Content */}
      <p className="text-sm text-brand-primary leading-relaxed whitespace-pre-wrap">{chunk.content}</p>
    </div>
  );
}
