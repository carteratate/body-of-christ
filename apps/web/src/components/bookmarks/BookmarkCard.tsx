"use client";

import { useState } from "react";
import { Bookmark as BookmarkIcon, BookOpen, Copy, ExternalLink, Pencil, Plus } from "lucide-react";
import { updateBookmarkNote, type Bookmark } from "@/lib/api";
import { trackBookmarkDeleted, trackDocumentOpened } from "@/lib/analytics";
import { getCollectionMeta } from "@/lib/collections";
import { stripVerseMarkers } from "@/lib/verse-markers";
import { contentWithMarkers, footnotesCopyText, parseFootnotes } from "@/lib/footnotes";
import { readerHref } from "@/lib/readerNavigation";
import { excerptSourceCredit, excerptSourceUrl, isExcerptOnly } from "@/lib/reader-access";
import { useReaderReturnKey } from "@/lib/useReaderReturnKey";
import { IntentLink, ThemedTooltip } from "@/components/common";
import { MovedNote, PassageFacts, RemovalNotice } from "@/components/common/PassageFacts";
import { sourceCreditOf } from "@/lib/attribution";
import { parseTombstone } from "@/lib/corpus-lifecycle";
import { PassageNotes, PassageText } from "@/components/common/PassageText";

const NOTE_MAX = 3000;

interface BookmarkCardProps {
  bookmark: Bookmark;
  token: string | null;
  onRemove: (bookmark: Bookmark) => Promise<void>;
  onNoteUpdated: (bookmarkId: string, note: string | null) => void;
  showToast: (message: string, type?: "success" | "error") => void;
}

export function BookmarkCard({ bookmark, token, onRemove, onNoteUpdated, showToast }: BookmarkCardProps) {
  const [editing, setEditing] = useState(false);
  const [draftNote, setDraftNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  // Stable between navigations, so the reader href is the URL its prefetch
  // warmed; the marker is written only for a same-tab navigation.
  const { returnKey, markReturn } = useReaderReturnKey("saved");

  // ── Null chunk fallback ───────────────────────────────────────────────────
  if (bookmark.chunk === null) {
    return (
      <div className="rounded-lg bg-brand-surface border-[3px] border-brand-surface p-4 flex items-center justify-between gap-3">
        <p className="text-sm text-brand-muted italic">Passage unavailable</p>
        <ThemedTooltip label="Remove this unavailable passage from Saved Passages.">
          <button
            onClick={() => {
              if (token && !removing) void onRemove(bookmark);
            }}
            aria-label="Remove bookmark"
            className="p-1.5 rounded text-sm text-brand-accent transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            <BookmarkIcon size={16} />
          </button>
        </ThemedTooltip>
      </div>
    );
  }

  const { content, source } = bookmark.chunk;
  const footnotes = parseFootnotes(bookmark.chunk.footnotes, content);
  const { collection, document_title, reference } = source;
  const collectionMeta = getCollectionMeta(collection);
  const borderColor = collectionMeta?.color ?? "var(--color-brand-accent)";
  const displayReference = reference ?? document_title;
  // A removed passage shows why, and no text; the user's note stays (2.4a, 2.4b).
  const tombstone = bookmark.status === "removed" ? parseTombstone(bookmark.tombstone) : null;

  // ── Remove bookmark ───────────────────────────────────────────────────────
  async function handleRemove() {
    if (!token || removing) return;
    setRemoving(true);
    trackBookmarkDeleted({ collection });
    await onRemove(bookmark);
    setRemoving(false);
  }

  // ── Copy action ───────────────────────────────────────────────────────────
  function handleCopy() {
    const credited = sourceCredit ? `\n\n${sourceCredit}` : "";
    // Text, then its notes, then the credit, which stays last.
    const notes = footnotes.length ? `\n\n${footnotesCopyText(footnotes)}` : "";
    const body = footnotes.length ? contentWithMarkers(content, footnotes) : stripVerseMarkers(content);
    const text = `${body} — ${displayReference} (${collection})${notes}${credited}`;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text)
        .then(() => showToast("Copied"))
        .catch(() => showToast("Copy failed", "error"));
    }
  }

  // An excerpt-only document has no reader; link to its source instead (#265).
  const excerptOnly = isExcerptOnly(source);
  const sourceHref = excerptSourceUrl(source);
  const sourceCredit = sourceCreditOf(source.facts, excerptSourceCredit(source));
  const contextHref = readerHref({
    docId: source.document_id,
    origin: "saved",
    returnKey,
    anchor: source.anchor,
    chapter: source.chapter_key,
  });

  // ── Note actions ──────────────────────────────────────────────────────────
  function startAddNote() {
    setDraftNote("");
    setEditing(true);
  }

  function startEditNote() {
    setDraftNote(bookmark.note ?? "");
    setEditing(true);
  }

  function cancelEdit() {
    setDraftNote("");
    setEditing(false);
  }

  async function saveNote() {
    if (!token) return;
    const trimmed = draftNote.trim() || null;
    setSaving(true);
    try {
      await updateBookmarkNote(token, bookmark.id, trimmed);
      onNoteUpdated(bookmark.id, trimmed);
      setEditing(false);
      showToast(trimmed ? "Note saved" : "Note removed");
    } catch {
      showToast("Couldn't save note. Try again.", "error");
    } finally {
      setSaving(false);
    }
  }

  const atLimit = draftNote.length >= NOTE_MAX;

  return (
    <div
      className="overflow-hidden rounded-lg bg-brand-surface border-[3px] p-4"
      style={{ borderColor }}
    >
      {/* Top row: badge + reference + action buttons */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span
            className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border"
            style={{ borderColor: borderColor, color: borderColor }}
          >
            {collectionMeta?.label ?? collection}
          </span>
          <span className="text-sm text-brand-primary font-medium truncate">
            {displayReference}
          </span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {tombstone ? null : sourceHref ? (
            <ThemedTooltip label="Read the full text at its source.">
              <a
                href={sourceHref}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Read the full text at the source (opens in a new tab)"
                className="inline-flex p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
              >
                <ExternalLink size={16} />
              </a>
            </ThemedTooltip>
          ) : !excerptOnly && (
            <ThemedTooltip label="Open the passage in context to read the surrounding text.">
              <IntentLink
                href={contextHref}
                onClick={() => trackDocumentOpened({ documentId: source.document_id, collection, source: "saved" })}
                onNavigate={markReturn}
                aria-label="Open passage in context"
                className="inline-flex p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
              >
                <BookOpen size={16} />
              </IntentLink>
            </ThemedTooltip>
          )}
          <ThemedTooltip label="Remove this passage from Saved Passages.">
            <button onClick={handleRemove} disabled={removing} aria-label="Remove bookmark" className="p-1.5 rounded text-sm transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"><BookmarkIcon size={16} className="text-brand-accent" /></button>
          </ThemedTooltip>
          {!tombstone && (
            <ThemedTooltip label="Copy">
              <button onClick={handleCopy} aria-label="Copy passage" className="p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"><Copy size={16} /></button>
            </ThemedTooltip>
          )}
        </div>
      </div>

      {/* Passage content, or why it is gone */}
      {tombstone ? (
        <>
          <p className="-mt-1 mb-3 text-xs text-brand-muted">
            {[tombstone.title || document_title, tombstone.author ?? source.author].filter(Boolean).join(" · ")}
          </p>
          <RemovalNotice tombstone={tombstone} />
        </>
      ) : (
        <>
          {bookmark.status === "moved" && <MovedNote kind={bookmark.redirect?.kind} />}
          <PassageText content={content} footnotes={footnotes} />
          <PassageNotes footnotes={footnotes} />
          <PassageFacts
            facts={source.facts}
            passageNote={source.passage_note}
            language={source.language}
            credit={sourceCredit}
            supersededHref={source.facts?.superseded_by
              ? readerHref({ docId: source.facts.superseded_by, origin: "saved", returnKey: null })
              : null}
          />
        </>
      )}

      {/* ── Note section ──────────────────────────────────────────────────── */}
      <div
        className={`mt-3 ${editing || bookmark.note
          ? "-mx-4 -mb-4 border-t border-brand-muted/20 bg-brand-bg/20 px-4 py-3"
          : "pt-1"
        }`}
      >

        {/* Inline editor (add or edit) */}
        {editing && (
          <div className="flex flex-col gap-2">
            <label htmlFor={`bookmark-note-${bookmark.id}`} className="text-xs font-medium text-brand-accent">
              Your note
            </label>
            <textarea
              id={`bookmark-note-${bookmark.id}`}
              value={draftNote}
              onChange={(e) => setDraftNote(e.target.value)}
              maxLength={NOTE_MAX}
              rows={4}
              placeholder="Add context, a question, or why this passage matters..."
              autoFocus
              className="w-full min-h-[100px] resize-y rounded bg-brand-bg border border-brand-muted/40 px-3 py-2 text-sm text-brand-primary placeholder:text-brand-muted focus:outline-none focus:ring-1 focus:ring-brand-accent"
            />
            <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-col">
                <span className={`text-xs ${atLimit ? "text-brand-accent font-medium" : "text-brand-muted"}`}>
                  Private · {draftNote.length.toLocaleString()} / {NOTE_MAX.toLocaleString()}
                </span>
                {atLimit && (
                  <span className="text-xs text-brand-accent">
                    Character limit reached (3,000 max)
                  </span>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <button
                  onClick={cancelEdit}
                  disabled={saving}
                  className="px-3 py-1 rounded text-xs text-brand-muted border border-brand-muted/40 hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-accent disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={saveNote}
                  disabled={saving}
                  className="px-3 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-accent disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save note"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* No note + not editing: "Add note" button */}
        {!editing && !bookmark.note && (
          <button
            onClick={startAddNote}
            className="flex items-center gap-1.5 rounded text-xs text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-accent"
          >
            <Plus size={13} className="text-brand-accent" />
            Add a note
          </button>
        )}

        {/* Saved notes remain visible so passage and annotation read together. */}
        {!editing && bookmark.note && (
          <div id={`bookmark-note-content-${bookmark.id}`}>
            <div className="mb-1.5 flex items-center justify-between gap-3">
              <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-brand-accent">
                Note
              </span>
              <button
                onClick={startEditNote}
                className="flex items-center gap-1.5 rounded text-xs text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-accent"
              >
                <Pencil size={12} />
                Edit
              </button>
            </div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-brand-muted">
              {bookmark.note}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
