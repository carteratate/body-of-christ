"use client";

import { useState } from "react";
import { Bookmark, Copy, ThumbsUp, ThumbsDown, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import ReactDOM from "react-dom";
import { Toast, useToast } from "@/components/common";
import { useRouter } from "next/navigation";
import {
  addBookmark,
  removeBookmark,
  submitLabel,
  type ChunkResult,
} from "@/lib/api";
import {
  trackBookmarkCreated,
  trackBookmarkDeleted,
  trackDocumentOpened,
  trackExploreMoreClicked,
} from "@/lib/analytics";
import { getCollectionMeta } from "@/lib/collections";
import { renderVerseMarkers, stripVerseMarkers } from "@/lib/verse-markers";
import { useAppContext } from "@/components/layout/AppShell";

function hexToRgb(color: string): string {
  if (!color.startsWith("#") || color.length < 7) return "196,151,42";
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

interface ChunkCardProps {
  result: ChunkResult;
  index: number;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string, label: string) => void;
  isGuest?: boolean;
}

export function ChunkCard({ result, index, searchId, token, onExploreMore, isGuest = false }: ChunkCardProps) {
  const router = useRouter();
  const { chunk_id, content, source } = result;
  const { collection, document_title, author, reference, document_id } = source;

  const collectionMeta = getCollectionMeta(collection);
  const color = collectionMeta?.color ?? "var(--color-brand-accent)";
  const hex = collectionMeta?.hex ?? "#C4972A";
  const rgb = hexToRgb(hex);

  const primaryReference =
    collection === "church-fathers" && reference && document_title
      ? `${document_title}, ${reference}`
      : reference ?? document_title;

  const showAuthor = !!author && (collection === "church-fathers" || collection === "encyclicals");

  const { toast, showToast, dismissToast } = useToast();
  const { bookmarkIds, setBookmarkForChunk } = useAppContext();

  const [isExpanded, setIsExpanded] = useState(false);

  // ── Bookmark state ────────────────────────────────────────────────────────
  const bookmarkId = bookmarkIds[chunk_id] ?? null;
  const isBookmarked = bookmarkId !== null;
  const [bookmarkPending, setBookmarkPending] = useState(false);

  async function handleBookmark() {
    if (!token || bookmarkPending) return;
    const previousId = bookmarkId;
    setBookmarkPending(true);
    try {
      if (isBookmarked && bookmarkId) {
        setBookmarkForChunk(chunk_id, null);
        await removeBookmark(token, bookmarkId);
        trackBookmarkDeleted({ collection });
      } else {
        setBookmarkForChunk(chunk_id, "pending");
        const res = await addBookmark(token, chunk_id);
        setBookmarkForChunk(chunk_id, res.id);
        trackBookmarkCreated({ collection, rankPositionWhenSaved: index });
        showToast("Saved to your passages");
      }
    } catch {
      setBookmarkForChunk(chunk_id, previousId);
      showToast("Couldn't save. Try again.", "error");
    } finally {
      setBookmarkPending(false);
    }
  }

  // ── Copy action ───────────────────────────────────────────────────────────
  function handleCopy() {
    const citation = showAuthor ? `${primaryReference} (${author})` : primaryReference;
    const text = `${stripVerseMarkers(content)} — ${citation} (${collection})`;
    navigator.clipboard.writeText(text)
      .then(() => showToast("Copied"))
      .catch(() => showToast("Copy failed", "error"));
  }

  // ── Read More action ──────────────────────────────────────────────────────
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  function handleReadMore() {
    if (!UUID_RE.test(document_id)) return;
    trackDocumentOpened({ documentId: document_id, collection, source: "chunk_card" });
    const anchor = source.anchor;
    const qs = anchor ? `?anchor=${encodeURIComponent(anchor)}` : "";
    router.push(`/reader/${document_id}${qs}`);
  }

  // ── Feedback state ────────────────────────────────────────────────────────
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [feedbackPending, setFeedbackPending] = useState(false);

  async function handleFeedback(direction: "up" | "down") {
    if (!token || !searchId || feedback === direction || feedbackPending) return;
    const previous = feedback;
    setFeedback(direction);
    setFeedbackPending(true);
    try {
      await submitLabel(token, chunk_id, direction, searchId);
    } catch {
      setFeedback(previous);
      showToast("Couldn't record feedback. Try again.", "error");
    } finally {
      setFeedbackPending(false);
    }
  }

  // ── Explore more action ───────────────────────────────────────────────────
  function handleExploreMore() {
    trackExploreMoreClicked({ collection, source: "chunk_card" });
    onExploreMore(stripVerseMarkers(content), primaryReference ?? "");
  }

  // ── Collection badge label ────────────────────────────────────────────────
  const translation = collection === "bible" && source.metadata?.translation
    ? ` · ${String(source.metadata.translation)}`
    : "";
  const badgeLabel = `${collectionMeta?.label ?? collection}${translation}`;

  return (
    <div
      style={{
        borderRadius: "8px",
        overflow: "hidden",
        border: `1px solid rgba(${rgb},0.7)`,
        background: `rgba(${rgb},0.32)`,
      }}
    >
      {/* ── Header — always visible, click to expand ── */}
      <button
        onClick={() => setIsExpanded((v) => !v)}
        style={{
          width: "100%",
          background: "transparent",
          border: "none",
          borderBottom: isExpanded ? `1px solid rgba(${rgb},0.25)` : "none",
          padding: "10px 14px",
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          textAlign: "left",
          userSelect: "none",
        }}
      >
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span
            className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border shrink-0"
            style={{ borderColor: color, color }}
          >
            {badgeLabel}
          </span>
          <div className="min-w-0">
            {showAuthor && (
              <p className="text-xs text-brand-primary truncate leading-tight">{author}</p>
            )}
            <p className="text-sm text-brand-primary font-semibold truncate">{primaryReference}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-3">
          {result.reranker_score !== null && (
            <div className="flex items-center gap-1.5">
              <span className="text-brand-primary max-md:hidden" style={{ fontSize: "11px" }}>Relevance Score:</span>
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--color-brand-primary)",
                  background: `rgba(${rgb},0.12)`,
                  border: `2px solid rgba(${rgb},0.8)`,
                  borderRadius: "4px",
                  padding: "1px 6px",
                }}
              >
                {Math.round(result.reranker_score * 100)}%
              </span>
            </div>
          )}
          {isExpanded
            ? <ChevronUp size={15} className="text-brand-muted" />
            : <ChevronDown size={15} className="text-brand-muted" />
          }
        </div>
      </button>

      {/* ── Expanded body ── */}
      {isExpanded && (
        <div style={{ background: "transparent", padding: "16px" }}>
          {/* Content */}
          <p className="text-sm text-brand-primary leading-relaxed whitespace-pre-wrap">{renderVerseMarkers(content)}</p>

          {/* Relevance explanation */}
          {result.explanation !== "" && (
            <div
              style={{
                marginTop: "12px",
                borderRadius: "6px",
                padding: "12px",
                background: `rgba(${rgb},0.06)`,
                border: `1px solid rgba(${rgb},0.15)`,
              }}
            >
              <div className="flex items-center gap-1.5 mb-1.5">
                <Sparkles size={11} style={{ color }} />
                <span style={{ fontSize: "10px", color, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Why this is relevant
                </span>
              </div>
              {result.explanation === null ? (
                <div className="animate-pulse space-y-2">
                  <div className="h-3 rounded w-full" style={{ background: `rgba(${rgb},0.12)` }} />
                  <div className="h-3 rounded w-5/6" style={{ background: `rgba(${rgb},0.12)` }} />
                  <div className="h-3 rounded w-3/4" style={{ background: `rgba(${rgb},0.12)` }} />
                </div>
              ) : (
                <p className="text-sm text-brand-primary leading-relaxed">{result.explanation}</p>
              )}
            </div>
          )}

          {/* Action row */}
          {!isGuest && (
            <div className="flex items-center justify-between mt-3 gap-2 max-md:flex-wrap">
              {/* Left: bookmark + copy */}
              <div className="flex items-center gap-0.5">
                <button
                  onClick={handleBookmark}
                  title={isBookmarked ? "Remove bookmark" : "Save passage"}
                  aria-label={isBookmarked ? "Remove bookmark" : "Save passage"}
                  aria-busy={bookmarkPending}
                  disabled={bookmarkPending}
                  className="p-1.5 rounded transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent disabled:opacity-60"
                >
                  <Bookmark size={15} className={isBookmarked ? "text-brand-accent" : "text-brand-muted"} />
                </button>
                <button
                  onClick={handleCopy}
                  title="Copy passage"
                  aria-label="Copy passage"
                  className="p-1.5 rounded text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
                >
                  <Copy size={15} />
                </button>
              </div>

              {/* Right: feedback + read more + explore more */}
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleFeedback("up")}
                  title="Helpful"
                  aria-label="Mark as relevant"
                  disabled={feedbackPending || feedback === "up"}
                  className={`p-1.5 rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${
                    feedback === "up" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary disabled:opacity-50"
                  }`}
                >
                  <ThumbsUp size={15} />
                </button>
                <button
                  onClick={() => handleFeedback("down")}
                  title="Not helpful"
                  aria-label="Mark as not relevant"
                  disabled={feedbackPending || feedback === "down"}
                  className={`p-1.5 rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${
                    feedback === "down" ? "text-brand-danger" : "text-brand-muted hover:text-brand-primary disabled:opacity-50"
                  }`}
                >
                  <ThumbsDown size={15} />
                </button>
                <button
                  onClick={handleReadMore}
                  className="px-2 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
                >
                  Read in Context
                </button>
                <button
                  onClick={handleExploreMore}
                  aria-label="Query more like this"
                  className="px-2 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
                >
                  Query More Like This
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {toast.visible && typeof document !== "undefined" &&
        ReactDOM.createPortal(
          <Toast message={toast.message} type={toast.type} onDismiss={dismissToast} />,
          document.body
        )}
    </div>
  );
}
