"use client";

import { useState } from "react";
import ReactDOM from "react-dom";
import { Toast, useToast } from "@/components/common";
import { useRouter } from "next/navigation";
import {
  addBookmark,
  removeBookmark,
  submitFeedback,
  type ChunkResult,
} from "@/lib/api";
import {
  trackChunkLiked,
  trackChunkDisliked,
  trackBookmarkCreated,
  trackBookmarkDeleted,
  trackDocumentOpened,
  trackExploreMoreClicked,
} from "@/lib/analytics";
import { getCollectionMeta } from "@/lib/collections";
import { RelevanceExplanation } from "./RelevanceExplanation";

interface ChunkCardProps {
  result: ChunkResult;
  index: number;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string) => void;
}

export function ChunkCard({ result, index, searchId, token, onExploreMore }: ChunkCardProps) {
  const router = useRouter();
  const { chunk_id, content, source } = result;
  const { collection, document_title, reference, document_id } = source;

  const collectionMeta = getCollectionMeta(collection);
  const borderColor = collectionMeta?.color ?? "var(--color-brand-accent)";
  const displayReference = reference ?? document_title;

  const { toast, showToast, dismissToast } = useToast();

  // ── Bookmark state ────────────────────────────────────────────────────────
  const [isBookmarked, setIsBookmarked] = useState(false);
  const [bookmarkId, setBookmarkId] = useState<string | null>(null);

  async function handleBookmark() {
    if (!token) return;
    try {
      if (isBookmarked && bookmarkId) {
        await removeBookmark(token, bookmarkId);
        setIsBookmarked(false);
        setBookmarkId(null);
        trackBookmarkDeleted({ collection });
      } else {
        const result = await addBookmark(token, chunk_id);
        setBookmarkId(result.id);
        setIsBookmarked(true);
        trackBookmarkCreated({ collection, rankPositionWhenSaved: index });
        showToast("Saved to your passages");
      }
    } catch {
      showToast("Couldn't save. Try again.", "error");
    }
  }

  // ── Copy action ───────────────────────────────────────────────────────────
  function handleCopy() {
    const text = `${content} — ${displayReference} (${collection})`;
    navigator.clipboard.writeText(text)
      .then(() => showToast("Copied"))
      .catch(() => showToast("Copy failed", "error"));
  }

  // ── Read More action ──────────────────────────────────────────────────────
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  function handleReadMore() {
    if (!UUID_RE.test(document_id) || !UUID_RE.test(chunk_id)) return;
    trackDocumentOpened({ documentId: document_id, collection, source: "chunk_card" });
    router.push(`/reader/${document_id}?chunk_id=${chunk_id}`);
  }

  // ── Feedback state ────────────────────────────────────────────────────────
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);

  async function handleFeedback(direction: "up" | "down") {
    if (!token || feedback === direction) return;
    try {
      await submitFeedback(token, chunk_id, direction, searchId ?? undefined);
      setFeedback(direction);
      if (direction === "up") {
        trackChunkLiked({
          collection,
          documentTitle: document_title,
          rankPosition: index,
          searchId: searchId ?? "",
        });
      } else {
        trackChunkDisliked({
          collection,
          documentTitle: document_title,
          rankPosition: index,
          searchId: searchId ?? "",
        });
      }
    } catch {
      // silent failure
    }
  }

  // ── Explore more action ───────────────────────────────────────────────────
  function handleExploreMore() {
    const trimmed = content.slice(0, 200).replace(/\s+\S*$/, "");
    trackExploreMoreClicked({ collection, source: "chunk_card" });
    onExploreMore(trimmed);
  }

  // ── Collection badge label ────────────────────────────────────────────────
  const translation = collection === "bible" && source.metadata?.translation
    ? ` · ${String(source.metadata.translation)}`
    : "";
  const badgeLabel = `${collectionMeta?.label ?? collection}${translation}`;

  return (
    <div
      className="rounded-lg bg-brand-surface border-l-4 p-4"
      style={{ borderLeftColor: borderColor }}
    >
      {/* Top row: badge + reference + top-right actions */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {/* Collection badge */}
          <span
            className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border"
            style={{ borderColor: borderColor, color: borderColor }}
          >
            {badgeLabel}
          </span>
          {/* Reference */}
          <span className="text-sm text-brand-primary font-medium truncate">
            {displayReference}
          </span>
        </div>

        {/* Top-right actions */}
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

          {/* Read More */}
          <button
            onClick={handleReadMore}
            className="px-2 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            Read More
          </button>
        </div>
      </div>

      {/* Content */}
      <p className="text-sm text-brand-primary leading-relaxed whitespace-pre-wrap">{content}</p>

      {/* Relevance explanation */}
      <RelevanceExplanation explanation={result.explanation} />

      {/* Bottom row: feedback + explore more */}
      <div className="flex items-center justify-end gap-2 mt-3">
        {/* Thumbs up */}
        <button
          onClick={() => handleFeedback("up")}
          title="Helpful"
          aria-label="Mark as relevant"
          disabled={feedback === "up"}
          className={`p-1.5 rounded text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${
            feedback === "up"
              ? "text-brand-accent"
              : "text-brand-muted hover:text-brand-primary disabled:opacity-50"
          }`}
        >
          👍
        </button>

        {/* Thumbs down */}
        <button
          onClick={() => handleFeedback("down")}
          title="Not helpful"
          aria-label="Mark as not relevant"
          disabled={feedback === "down"}
          className={`p-1.5 rounded text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${
            feedback === "down"
              ? "text-brand-danger"
              : "text-brand-muted hover:text-brand-primary disabled:opacity-50"
          }`}
        >
          👎
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
      {toast.visible && typeof document !== "undefined" &&
        ReactDOM.createPortal(
          <Toast message={toast.message} type={toast.type} onDismiss={dismissToast} />,
          document.body
        )}
    </div>
  );
}
