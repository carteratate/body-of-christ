"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bookmark as BookmarkIcon, BookOpen, ChevronDown, ChevronUp, Copy, Pencil, Search } from "lucide-react";
import { updateBookmarkNote, type Bookmark } from "@/lib/api";
import { trackBookmarkDeleted, trackDocumentOpened, trackExploreMoreClicked } from "@/lib/analytics";
import { getCollectionMeta } from "@/lib/collections";
import { renderVerseMarkers, stripVerseMarkers } from "@/lib/verse-markers";
import { createReaderReturnKey } from "@/lib/readerNavigation";
import { ThemedTooltip } from "@/components/common";

const NOTE_MAX = 3000;

interface BookmarkCardProps {
  bookmark: Bookmark;
  token: string | null;
  onRemove: (bookmark: Bookmark) => Promise<void>;
  onNoteUpdated: (bookmarkId: string, note: string | null) => void;
  showToast: (message: string, type?: "success" | "error") => void;
}

export function BookmarkCard({ bookmark, token, onRemove, onNoteUpdated, showToast }: BookmarkCardProps) {
  const router = useRouter();
  const [noteOpen, setNoteOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftNote, setDraftNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);

  // ── Null chunk fallback ───────────────────────────────────────────────────
  if (bookmark.chunk === null) {
    return (
      <div className="rounded-lg bg-brand-surface border-l-4 border-brand-surface p-4 flex items-center justify-between gap-3">
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
  const { collection, document_title, reference } = source;
  const collectionMeta = getCollectionMeta(collection);
  const borderColor = collectionMeta?.color ?? "var(--color-brand-accent)";
  const displayReference = reference ?? document_title;

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
    const text = `${stripVerseMarkers(content)} — ${displayReference} (${collection})`;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text)
        .then(() => showToast("Copied"))
        .catch(() => showToast("Copy failed", "error"));
    }
  }

  // ── Explore more action ───────────────────────────────────────────────────
  function handleExploreMore() {
    trackExploreMoreClicked({ collection, source: "chunk_card" });
    router.push(
      `/search?explore=${encodeURIComponent(stripVerseMarkers(content))}&exploreRef=${encodeURIComponent(displayReference ?? "")}`
    );
  }

  function handleOpenContext() {
    const params = new URLSearchParams({ from: "saved" });
    const returnKey = createReaderReturnKey("saved");
    if (returnKey) params.set("returnKey", returnKey);
    if (source.anchor) params.set("anchor", source.anchor);
    else if (source.chapter_key) params.set("chapter", source.chapter_key);
    trackDocumentOpened({ documentId: source.document_id, collection, source: "saved" });
    router.push(`/reader/${source.document_id}?${params.toString()}`);
  }

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
      setNoteOpen(trimmed !== null);
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
      className="rounded-lg bg-brand-surface border-l-4 p-4"
      style={{ borderLeftColor: borderColor }}
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
          <ThemedTooltip label="Open this passage in the context of the full source">
            <button onClick={handleOpenContext} aria-label="Open passage in context" className="p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"><BookOpen size={16} /></button>
          </ThemedTooltip>
          <ThemedTooltip label="Remove this passage from Saved Passages.">
            <button onClick={handleRemove} disabled={removing} aria-label="Remove bookmark" className="p-1.5 rounded text-sm transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"><BookmarkIcon size={16} className="text-brand-accent" /></button>
          </ThemedTooltip>
          <ThemedTooltip label="Copy">
            <button onClick={handleCopy} aria-label="Copy passage" className="p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"><Copy size={16} /></button>
          </ThemedTooltip>
          <ThemedTooltip label="Start a new search to find passages similar to this one">
            <button onClick={handleExploreMore} aria-label="Query more like this" className="p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"><Search size={16} /></button>
          </ThemedTooltip>
        </div>
      </div>

      {/* Passage content */}
      <p className="text-sm text-brand-primary leading-relaxed whitespace-pre-wrap">
        {renderVerseMarkers(content)}
      </p>

      {/* ── Note section ──────────────────────────────────────────────────── */}
      <div className="mt-3 pt-3 border-t border-brand-surface/60">

        {/* Inline editor (add or edit) */}
        {editing && (
          <div className="flex flex-col gap-2">
            <label htmlFor={`bookmark-note-${bookmark.id}`} className="sr-only">
              Personal note for this saved passage
            </label>
            <textarea
              id={`bookmark-note-${bookmark.id}`}
              value={draftNote}
              onChange={(e) => setDraftNote(e.target.value)}
              maxLength={NOTE_MAX}
              rows={4}
              placeholder="Write your reflection..."
              autoFocus
              className="w-full min-h-[100px] resize-y rounded bg-brand-bg border border-brand-muted/40 px-3 py-2 text-sm text-brand-primary placeholder:text-brand-muted focus:outline-none focus:ring-1 focus:ring-brand-accent"
            />
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-col">
                <span className={`text-xs ${atLimit ? "text-brand-accent font-medium" : "text-brand-muted"}`}>
                  {draftNote.length.toLocaleString()} / {NOTE_MAX.toLocaleString()}
                </span>
                {atLimit && (
                  <span className="text-xs text-brand-accent">
                    Character limit reached (3,000 max)
                  </span>
                )}
              </div>
              <div className="flex gap-2">
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
                  {saving ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* No note + not editing: "Add note" button */}
        {!editing && !bookmark.note && (
          <button
            onClick={startAddNote}
            className="flex items-center gap-1.5 text-xs text-brand-muted hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-accent rounded"
          >
            <Pencil size={13} />
            Add note
          </button>
        )}

        {/* Note exists + not editing: collapse/expand toggle */}
        {!editing && bookmark.note && (
          <div>
            <button
              onClick={() => setNoteOpen((o) => !o)}
              aria-expanded={noteOpen}
              aria-controls={`bookmark-note-content-${bookmark.id}`}
              className="flex items-center gap-1.5 text-xs text-brand-muted hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-accent rounded"
            >
              {noteOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              Note
            </button>
            {noteOpen && (
              <div id={`bookmark-note-content-${bookmark.id}`} className="mt-2 pl-3 border-l-2 border-brand-muted/30">
                <p className="text-xs text-brand-muted leading-relaxed whitespace-pre-wrap">
                  {bookmark.note}
                </p>
                <button
                  onClick={startEditNote}
                  className="mt-2 flex items-center gap-1.5 text-xs text-brand-muted hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-accent rounded"
                >
                  <Pencil size={13} />
                  Edit
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
