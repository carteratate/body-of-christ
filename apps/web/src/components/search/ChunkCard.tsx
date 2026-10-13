"use client";

import { useState } from "react";
import { Bookmark, Copy, ThumbsUp, ThumbsDown, ChevronDown, ChevronUp } from "lucide-react";
import ReactDOM from "react-dom";
import { IntentLink, ThemedTooltip, Toast, useToast } from "@/components/common";
import { useSearchParams } from "next/navigation";
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
} from "@/lib/analytics";
import { AttachedPassage } from "./AttachedPassage";
import { RelevanceExplanation } from "./RelevanceExplanation";
import { getCollectionMeta } from "@/lib/collections";
import { displayRole } from "@/lib/passageRole";
import { renderVerseMarkers, stripVerseMarkers } from "@/lib/verse-markers";
import { useAppContext } from "@/components/layout/AppShell";
import { saveFeedbackContext } from "@/lib/feedbackContext";
import { readerHref } from "@/lib/readerNavigation";
import { useReaderReturnKey } from "@/lib/useReaderReturnKey";
import { useGuestGate } from "@/components/layout/guestGate";

function hexToRgb(color: string): string {
  if (!color.startsWith("#") || color.length < 7) return "196,151,42";
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

function mobileCitation(
  collection: string,
  documentTitle: string,
  reference: string | null,
  author: string | null,
): string {
  let citation = reference?.trim() || documentTitle;

  if (author && citation.startsWith(`${author} — `)) {
    citation = citation.slice(author.length + 3);
  }

  if (collection === "summa") {
    const match = citation.match(/^[^,]+,\s*(.+?),\s*Question\s+(\d+).*?,\s*Article\s+(\d+)/i);
    if (match) return `${match[1]} · Q. ${match[2]} · Art. ${match[3]}`;
  }

  if (collection === "canon-law") {
    const canon = citation.match(/\bCan\.\s*[\d–-]+(?:\s*§+\s*\d+)?/i);
    if (canon) return canon[0];
  }

  return citation;
}

/**
 * The passage's role, shown beside its citation.
 *
 * A collapsed card is the default state and shows only a citation, so without this an
 * objection is indistinguishable from Aquinas's own teaching until the user expands it.
 * Kept on the same line as the reference, so it survives the card's fixed-height header
 * at every breakpoint — but as a SIBLING of the truncating element, never inside it.
 * A Summa reference averages 214 characters and overflows the desktop column, so a tag
 * appended within the truncated text is ellipsed away before it is painted: 97% of
 * objection cards would silently lose the marker on the exact surface it exists for.
 */
function RoleTag({ role, color }: { role: string; color: string }) {
  return (
    <span
      className="ml-1.5 shrink-0 whitespace-nowrap text-xs font-medium"
      style={{ color }}
    >
      · {role}
    </span>
  );
}

interface ChunkCardProps {
  result: ChunkResult;
  index: number;
  searchId: string | null;
  token: string;
  isGuest?: boolean;
  onExpand?: () => void;
  showOpenContextHint?: boolean;
  onDismissOpenContextHint?: () => void;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function ChunkCard({ result, index, searchId, token, isGuest = false, onExpand, showOpenContextHint = false, onDismissOpenContextHint }: ChunkCardProps) {
  const searchParams = useSearchParams();
  const { chunk_id, content, source } = result;
  // Presentation only. Copying and saving still address the passage the user matched.
  const attached = result.context ?? null;
  const { collection, document_title, author, reference, document_id } = source;
  // The passage's own role. Ingest moved "Objection N" out of `content`, so without this
  // an objection reads as a flat assertion wherever it travels without its attachment —
  // collapsed, copied, or announced.
  const role = displayRole(collection, source.unit_label, reference);

  const collectionMeta = getCollectionMeta(collection);
  const color = collectionMeta?.color ?? "var(--color-brand-accent)";
  const hex = collectionMeta?.hex ?? "#C4972A";
  const rgb = hexToRgb(hex);

  const primaryReference =
    collection === "church-fathers" && reference && document_title
      ? `${document_title}, ${reference}`
      : reference ?? document_title;

  const displayAuthor = author?.trim() === "Catholic Church" ? null : author;
  const showAuthor = !!displayAuthor;
  const includeAuthorInCopy = !!author && (collection === "church-fathers" || collection === "encyclicals");
  const compactReference = mobileCitation(collection, document_title, reference, author);

  const { toast, showToast, dismissToast } = useToast();
  const { bookmarkIds, setBookmarkForChunk } = useAppContext();
  const guestGate = useGuestGate();

  const [isExpanded, setIsExpanded] = useState(false);

  // ── Bookmark state ────────────────────────────────────────────────────────
  const bookmarkId = bookmarkIds[chunk_id] ?? null;
  const isBookmarked = isGuest ? (guestGate?.savedChunkIds.includes(chunk_id) ?? false) : bookmarkId !== null;
  const [bookmarkPending, setBookmarkPending] = useState(false);

  async function handleBookmark() {
    if (isGuest) {
      const saved = guestGate?.toggleSavedChunk(chunk_id) ?? false;
      if (saved) {
        showToast("Saved for this trial");
        guestGate?.requestSignup("saved");
      }
      return;
    }
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
    const citation = includeAuthorInCopy ? `${primaryReference} (${author})` : primaryReference;
    // The role goes in the citation, not the body: the body is the passage as written,
    // and the clipboard is the one place this text leaves the app entirely.
    const cited = role ? `${citation}, ${role}` : citation;
    const text = `${stripVerseMarkers(content)} — ${cited} (${collection})`;
    navigator.clipboard.writeText(text)
      .then(() => showToast("Copied"))
      .catch(() => showToast("Copy failed", "error"));
  }

  // ── Open in Context ───────────────────────────────────────────────────────
  // The href is built at render with a return key that holds steady between
  // navigations, so it is exactly the URL a hover prefetch warmed. The marker is
  // written only for a same-tab navigation (see useReaderReturnKey); a new tab
  // takes the reader's deep-link fallback.
  const { returnKey, markReturn } = useReaderReturnKey("search");
  const canOpenContext = UUID_RE.test(document_id);
  const contextHref = readerHref({
    docId: document_id,
    origin: "search",
    returnKey,
    anchor: source.anchor,
    chapter: source.chapter_key,
    guest: isGuest,
    guideBack: showOpenContextHint,
    preview: searchParams.get("preview") === "1",
  });
  function handleOpenContextClick() {
    onDismissOpenContextHint?.();
    trackDocumentOpened({ documentId: document_id, collection, source: "chunk_card" });
  }

  // ── Feedback state ────────────────────────────────────────────────────────
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [feedbackPending, setFeedbackPending] = useState(false);
  const [showReportPrompt, setShowReportPrompt] = useState(false);

  async function handleFeedback(direction: "up" | "down") {
    if (!token || !searchId || feedback === direction || feedbackPending) return;
    const previous = feedback;
    setFeedback(direction);
    setFeedbackPending(true);
    try {
      await submitLabel(token, chunk_id, direction, searchId);
      setShowReportPrompt(direction === "down");
    } catch {
      setFeedback(previous);
      showToast("Couldn't record feedback. Try again.", "error");
    } finally {
      setFeedbackPending(false);
    }
  }

  function reportResultProblem() {
    if (!searchId) return;
    saveFeedbackContext({
      category: "content",
      origin: "search_result",
      route: "/search",
      search_id: searchId,
      chunk_id,
      document_id,
    });
  }

  // ── Collection badge label ────────────────────────────────────────────────
  const translation = collection === "bible" && source.metadata?.translation
    ? ` · ${String(source.metadata.translation)}`
    : "";
  const badgeLabel = `${collectionMeta?.label ?? collection}${translation}`;
  const accessibleSummary = [
    badgeLabel,
    displayAuthor,
    primaryReference,
    role,
    result.reranker_score !== null ? `${Math.round(result.reranker_score * 100)}% relevance` : null,
  ].filter(Boolean).join(", ");

  return (
    <div
      className="min-w-0 overflow-hidden"
      style={{
        borderRadius: "8px",
        border: `1px solid rgba(${rgb},0.7)`,
        background: `rgba(${rgb},0.32)`,
      }}
    >
      {/* ── Header disclosure ── */}
      <div className="flex h-[96px] items-stretch p-3 sm:h-[68px]" style={{ borderBottom: isExpanded ? `1px solid rgba(${rgb},0.25)` : "none" }}>
        <button
          type="button"
          onClick={() => {
            if (!isExpanded) onExpand?.();
            setIsExpanded((value) => !value);
          }}
          aria-label={isExpanded ? `Collapse result: ${accessibleSummary}` : `Expand result: ${accessibleSummary}`}
          aria-expanded={isExpanded}
          aria-controls={`chunk-body-${chunk_id}`}
          className="relative flex min-h-11 min-w-0 flex-1 items-center rounded-md bg-transparent text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-accent"
        >
          <div className="flex min-w-0 flex-1 flex-col justify-center gap-1 pr-12 sm:hidden">
            <div className="flex min-w-0 items-center gap-2 pr-4">
              <span className="inline-flex max-w-[10rem] shrink-0 items-center truncate rounded-full border px-2 py-0.5 text-xs font-medium" style={{ borderColor: color, color }}>{badgeLabel}</span>
              {role && <RoleTag role={role} color={color} />}
              {displayAuthor && <span className="min-w-0 flex-1 truncate text-xs leading-tight text-brand-muted">{displayAuthor}</span>}
            </div>
            <p className="line-clamp-2 text-sm font-semibold leading-tight text-brand-primary">{compactReference}</p>
          </div>
          {result.reranker_score !== null && (
            <span
              className="absolute right-0 top-1/2 -translate-y-1/2 sm:hidden"
              style={{ fontSize: "11px", color: "var(--color-brand-primary)", background: `rgba(${rgb},0.12)`, border: `2px solid rgba(${rgb},0.8)`, borderRadius: "4px", padding: "1px 6px" }}
            >
              {Math.round(result.reranker_score * 100)}%
            </span>
          )}
          {isExpanded
            ? <ChevronUp size={15} className="absolute right-0 top-[-3px] text-brand-muted sm:hidden" />
            : <ChevronDown size={15} className="absolute right-0 top-[-3px] text-brand-muted sm:hidden" />}

          <div className="hidden min-w-0 flex-1 items-center sm:flex">
            <div className="flex min-w-0 flex-1 items-center gap-2 pr-[70px]">
              <span className="inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs font-medium" style={{ borderColor: color, color }}>{badgeLabel}</span>
              <div className="grid min-w-0 flex-1 grid-rows-[1rem_1rem] content-center overflow-hidden">
                <p className="truncate text-xs leading-tight text-brand-muted">{showAuthor ? displayAuthor : "\u00a0"}</p>
                <div className="flex min-w-0 items-baseline">
                  <span className="truncate text-sm font-semibold leading-tight text-brand-primary">{primaryReference}</span>
                  {role && <RoleTag role={role} color={color} />}
                </div>
              </div>
            </div>
          </div>
          {result.reranker_score !== null && (
            <span
              className="absolute right-[18px] top-1/2 hidden -translate-y-1/2 sm:block"
              style={{ fontSize: "11px", color: "var(--color-brand-primary)", background: `rgba(${rgb},0.12)`, border: `2px solid rgba(${rgb},0.8)`, borderRadius: "4px", padding: "1px 6px" }}
            >
              {Math.round(result.reranker_score * 100)}%
            </span>
          )}
          {isExpanded
            ? <ChevronUp size={15} className="absolute right-0 top-[-5px] hidden text-brand-muted sm:block" />
            : <ChevronDown size={15} className="absolute right-0 top-[-5px] hidden text-brand-muted sm:block" />}
        </button>
      </div>

      {/* ── Expanded body ── */}
      {isExpanded && (
        <div id={`chunk-body-${chunk_id}`} style={{ background: "transparent", padding: "16px" }}>
          {/* Content, with the passage that completes it. `relation` decides the side:
              a matched objection is followed by Aquinas's answer; a matched reply is
              PRECEDED by the objection it answers, because it opens mid-thought. */}
          {attached?.relation === "answers" && (
            <AttachedPassage context={attached} color={color} rgb={rgb} />
          )}
          <p className="text-sm text-brand-primary leading-relaxed whitespace-pre-wrap">{renderVerseMarkers(content)}</p>
          {attached?.relation === "answered_by" && (
            <AttachedPassage context={attached} color={color} rgb={rgb} />
          )}

          <RelevanceExplanation explanation={result.explanation} chunkId={chunk_id} color={color} rgb={rgb} />

          {/* Action row */}
          <div className="flex items-center justify-between mt-3 gap-2 max-md:flex-wrap">
            <div className="flex items-center gap-0.5">
              <ThemedTooltip label={isBookmarked ? "Remove this passage from Saved Passages." : "Save Passage"}>
                <button onClick={handleBookmark} aria-label={isBookmarked ? "Remove bookmark" : "Save passage"} aria-busy={bookmarkPending} disabled={bookmarkPending} className="p-1.5 rounded transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent disabled:opacity-60">
                  <Bookmark size={15} className={isBookmarked ? "text-brand-accent" : "text-brand-muted"} />
                </button>
              </ThemedTooltip>
              <ThemedTooltip label="Copy">
                <button onClick={handleCopy} aria-label="Copy passage" className="p-1.5 rounded text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
                  <Copy size={15} />
                </button>
              </ThemedTooltip>
            </div>

            <div className="flex max-w-full flex-wrap items-center justify-end gap-1.5">
              {!isGuest && <>
                <ThemedTooltip label="Tell TheoCorpus this result helped answer your question.">
                  <button onClick={() => handleFeedback("up")} aria-label="Mark as relevant" disabled={feedbackPending || feedback === "up"} className={`p-1.5 rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${feedback === "up" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary disabled:opacity-50"}`}><ThumbsUp size={15} /></button>
                </ThemedTooltip>
                <ThemedTooltip label="Tell TheoCorpus this result was not useful.">
                  <button onClick={() => handleFeedback("down")} aria-label="Mark as not relevant" disabled={feedbackPending || feedback === "down"} className={`p-1.5 rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${feedback === "down" ? "text-brand-danger" : "text-brand-muted hover:text-brand-primary disabled:opacity-50"}`}><ThumbsDown size={15} /></button>
                </ThemedTooltip>
              </>}
              <div className="relative">
                {showOpenContextHint && canOpenContext && (
                  <div role="status" className="absolute bottom-[calc(100%+10px)] right-0 z-20 w-56 rounded-lg border border-brand-accent/40 bg-brand-surface px-3 py-2 text-xs leading-relaxed text-brand-primary shadow-xl after:absolute after:-bottom-1.5 after:right-6 after:h-3 after:w-3 after:rotate-45 after:border-b after:border-r after:border-brand-accent/40 after:bg-brand-surface">
                    <button type="button" onClick={onDismissOpenContextHint} aria-label="Dismiss context guidance" className="absolute right-1.5 top-1 text-brand-muted hover:text-brand-primary">×</button>
                    <span className="block pr-3">Open the passage in context to read the surrounding text.</span>
                  </div>
                )}
                {canOpenContext && (
                  <IntentLink
                    href={contextHref}
                    onClick={handleOpenContextClick}
                    onNavigate={markReturn}
                    className="inline-block px-2 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
                  >
                    Open in Context
                  </IntentLink>
                )}
              </div>
            </div>
          </div>
          {showReportPrompt && searchId && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-md border border-brand-muted/25 bg-brand-bg/40 px-3 py-2 text-xs text-brand-muted">
              <span>Thanks. Is there a specific problem with this result?</span>
              <span className="flex gap-3">
                <button type="button" onClick={() => setShowReportPrompt(false)} className="hover:text-brand-primary">No, thanks</button>
                <IntentLink href="/feedback" onClick={reportResultProblem} className="font-medium text-brand-accent hover:underline">Report a problem</IntentLink>
              </span>
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
