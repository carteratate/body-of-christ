# Bookmark Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow each user to attach a personal note (up to 3,000 characters) to any saved passage bookmark, with inline editing and collapse/expand UX on the Saved Passages page.

**Architecture:** A nullable `note text` column is added to the existing `bookmarks` table via migration. A new `PATCH /v1/bookmarks/{id}` endpoint updates the note. The `GET /v1/bookmarks` response already returns all bookmark fields, so `note` is simply added to the SELECT and response model — no new query needed. `BookmarkCard.tsx` manages all note UI state locally.

**Tech Stack:** Python FastAPI + asyncpg (backend), Next.js 14 + TypeScript + Tailwind (frontend), Supabase Postgres (DB), Pydantic v2 (validation).

## Global Constraints

- All API endpoints must be under `/v1/`.
- JWT auth required on every endpoint — `Depends(get_current_user)`.
- Parameterized queries only — no string interpolation in SQL.
- Ownership check on every write: `WHERE id = $1 AND user_id = $2`.
- Note max length: 3,000 characters — enforced at Pydantic layer (primary) and DB CHECK constraint (backstop).
- Note content MUST render via JSX text interpolation only (`{note}`). `dangerouslySetInnerHTML` is prohibited.
- Follow existing file patterns: models in `services/api/app/models/`, routes in `services/api/app/routes/`, frontend API calls centralized in `apps/web/src/lib/api.ts`.
- Invalidate `_bookmarks_cache` on every write that touches the bookmarks table.

---

## File Map

| Action | File | What changes |
|---|---|---|
| Create | `supabase/migrations/0016_bookmarks_add_note.sql` | Adds `note text` column + CHECK constraint |
| Modify | `services/api/app/models/bookmarks.py` | Adds `BookmarkNoteUpdate`; adds `note` field to `BookmarkResponse` |
| Modify | `services/api/app/routes/bookmarks.py` | Updates GET query to include `b.note`; adds PATCH endpoint + write rate limiter |
| Modify | `apps/web/src/lib/api.ts` | Adds `note` to `Bookmark` interface; adds `updateBookmarkNote` function |
| Modify | `apps/web/src/components/bookmarks/BookmarkCard.tsx` | Full note UI: add, collapse/expand, inline edit, char counter |
| Modify | `apps/web/src/components/bookmarks/BookmarksPage.tsx` | Adds `onNoteUpdated` prop to `BookmarkCard` and local state handler |

---

## Task 1: DB Migration

**Files:**
- Create: `supabase/migrations/0016_bookmarks_add_note.sql`

**Interfaces:**
- Produces: `bookmarks.note` — nullable `text` column, `char_length(note) <= 3000` enforced at DB level

- [ ] **Step 1: Create the migration file**

Create `supabase/migrations/0016_bookmarks_add_note.sql` with this exact content:

```sql
-- Add personal note to bookmarks (one note per saved passage).
-- Nullable: existing rows get NULL. CHECK constraint is defense-in-depth;
-- primary enforcement is in the Pydantic model layer.
alter table bookmarks
  add column note text check (char_length(note) <= 3000);
```

- [ ] **Step 2: Apply the migration**

```bash
supabase db push
```

Expected: migration applies cleanly with no errors. If `supabase db push` is unavailable, run via Supabase Studio SQL editor.

- [ ] **Step 3: Verify the column exists**

In Supabase Studio or via `psql`, run:
```sql
select column_name, data_type, is_nullable
from information_schema.columns
where table_name = 'bookmarks' and column_name = 'note';
```

Expected output:
```
column_name | data_type | is_nullable
note        | text      | YES
```

- [ ] **Step 4: Verify the CHECK constraint**

```sql
select con.conname, pg_get_constraintdef(con.oid)
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
where rel.relname = 'bookmarks' and con.contype = 'c';
```

Expected: a row like `bookmarks_note_check | CHECK (char_length(note) <= 3000)`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0016_bookmarks_add_note.sql
git commit -m "feat(db): add note column to bookmarks"
```

---

## Task 2: Backend Pydantic Models

**Files:**
- Modify: `services/api/app/models/bookmarks.py`

**Interfaces:**
- Consumes: nothing from prior tasks
- Produces:
  - `BookmarkNoteUpdate` — request body for PATCH endpoint: `note: Optional[str]` with `max_length=3000`
  - `BookmarkResponse.note` — `Optional[str] = None` field on existing response model

- [ ] **Step 1: Update `models/bookmarks.py`**

Replace the entire file with:

```python
from pydantic import BaseModel, Field
from typing import Optional


class BookmarkCreate(BaseModel):
    chunk_id: str


class BookmarkNoteUpdate(BaseModel):
    note: Optional[str] = Field(None, max_length=3000)


class BookmarkSource(BaseModel):
    collection: str
    document_title: str
    author: Optional[str] = None
    reference: Optional[str] = None


class BookmarkChunk(BaseModel):
    content: str
    source: BookmarkSource


class BookmarkResponse(BaseModel):
    id: str
    chunk_id: str
    created_at: str
    note: Optional[str] = None
    chunk: Optional[BookmarkChunk] = None


class BookmarkListResponse(BaseModel):
    bookmarks: list[BookmarkResponse]
```

- [ ] **Step 2: Verify Pydantic validation rejects oversized notes**

Run a quick Python sanity check from the `services/api/` directory:

```bash
cd services/api
python -c "
from app.models.bookmarks import BookmarkNoteUpdate
from pydantic import ValidationError
try:
    BookmarkNoteUpdate(note='x' * 3001)
    print('FAIL: should have raised')
except ValidationError as e:
    print('PASS:', e.errors()[0]['type'])
"
```

Expected output: `PASS: string_too_long`

- [ ] **Step 3: Verify None is accepted**

```bash
python -c "
from app.models.bookmarks import BookmarkNoteUpdate
m = BookmarkNoteUpdate(note=None)
print('PASS note=None:', m.note)
m2 = BookmarkNoteUpdate(note='hello')
print('PASS note=hello:', m2.note)
"
```

Expected:
```
PASS note=None: None
PASS note=hello: hello
```

- [ ] **Step 4: Commit**

```bash
cd ../..
git add services/api/app/models/bookmarks.py
git commit -m "feat(api): add BookmarkNoteUpdate model and note field to BookmarkResponse"
```

---

## Task 3: Backend PATCH Endpoint + GET Update

**Files:**
- Modify: `services/api/app/routes/bookmarks.py`

**Interfaces:**
- Consumes:
  - `BookmarkNoteUpdate` from `app.models.bookmarks`
  - `BookmarkResponse`, `BookmarkChunk`, `BookmarkSource`, `BookmarkListResponse` from `app.models.bookmarks`
- Produces:
  - `GET /v1/bookmarks` — now includes `note` on each bookmark
  - `PATCH /v1/bookmarks/{bookmark_id}` — updates `note`, returns updated `BookmarkResponse`

- [ ] **Step 1: Update the GET query to include `b.note`**

In `services/api/app/routes/bookmarks.py`, find the `list_bookmarks` function. Update the SQL query to add `b.note`:

```python
        rows = await pool.fetch(
            """
            SELECT b.id, b.chunk_id, b.created_at, b.note,
                   c.content, c.reference,
                   d.collection, d.title AS document_title, d.author
            FROM bookmarks b
            JOIN chunks c ON c.id = b.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE b.user_id = $1
            ORDER BY b.created_at DESC
            """,
            user.user_id,
        )
```

Update the `BookmarkResponse(...)` construction inside `list_bookmarks` to pass `note`:

```python
    response = BookmarkListResponse(
        bookmarks=[
            BookmarkResponse(
                id=str(row["id"]),
                chunk_id=str(row["chunk_id"]),
                created_at=row["created_at"].isoformat(),
                note=row["note"],
                chunk=BookmarkChunk(
                    content=row["content"],
                    source=BookmarkSource(
                        collection=row["collection"],
                        document_title=row["document_title"],
                        author=row["author"],
                        reference=row["reference"],
                    ),
                ),
            )
            for row in rows
        ]
    )
```

- [ ] **Step 2: Add the write rate limiter and import `BookmarkNoteUpdate`**

Add to the imports at the top of the file:

```python
import time
from collections import defaultdict
```

Update the models import to include `BookmarkNoteUpdate`:

```python
from app.models.bookmarks import (
    BookmarkChunk,
    BookmarkCreate,
    BookmarkListResponse,
    BookmarkNoteUpdate,
    BookmarkResponse,
    BookmarkSource,
)
```

After the existing `_bookmarks_cache` and `_invalidate_bookmarks` definitions, add the write rate limiter:

```python
# In-memory per-user write rate limiter (20 writes/min).
# Uses a separate bucket from search/chat quotas to avoid cross-contamination.
_write_rate_timestamps: dict[str, list[float]] = defaultdict(list)
_WRITE_RATE_LIMIT = 20


def _check_write_rate_limit(user_id: str) -> None:
    now = time.time()
    window = [t for t in _write_rate_timestamps[user_id] if now - t < 60]
    _write_rate_timestamps[user_id] = window
    if len(window) >= _WRITE_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again in a moment.",
            headers={"Retry-After": "60"},
        )
    _write_rate_timestamps[user_id].append(now)
```

- [ ] **Step 3: Add the PATCH endpoint**

Add this new endpoint after the `create_bookmark` endpoint (before `list_bookmarks`):

```python
@router.patch("/bookmarks/{bookmark_id}", response_model=BookmarkResponse)
async def update_bookmark_note(
    bookmark_id: str,
    body: BookmarkNoteUpdate,
    user: AuthUser = Depends(get_current_user),
) -> BookmarkResponse:
    """Update the personal note on a bookmark owned by the authenticated user."""
    _check_write_rate_limit(str(user.user_id))

    try:
        bookmark_uuid = uuid.UUID(bookmark_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid bookmark_id: must be a UUID")

    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        row = await pool.fetchrow(
            """
            UPDATE bookmarks
            SET note = $1
            WHERE id = $2 AND user_id = $3
            RETURNING id, chunk_id, created_at, note
            """,
            body.note,
            bookmark_uuid,
            user.user_id,
        )
    except Exception as exc:
        logger.error("update_bookmark_note failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    _invalidate_bookmarks(user.user_id)

    return BookmarkResponse(
        id=str(row["id"]),
        chunk_id=str(row["chunk_id"]),
        created_at=row["created_at"].isoformat(),
        note=row["note"],
    )
```

- [ ] **Step 4: Start the API server and verify GET returns `note`**

```bash
cd services/api
uvicorn app.main:app --reload --port 8000
```

In a second terminal, call the bookmarks list (replace `<TOKEN>` with a real JWT from the browser dev tools):

```bash
curl -s -H "Authorization: Bearer <TOKEN>" http://localhost:8000/v1/bookmarks | python -m json.tool | grep note
```

Expected: each bookmark object contains `"note": null` (or a string if one was previously set).

- [ ] **Step 5: Verify PATCH updates the note**

```bash
# Get a bookmark ID from the list response, then:
curl -s -X PATCH \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"note": "This passage speaks to me because..."}' \
  http://localhost:8000/v1/bookmarks/<BOOKMARK_ID> | python -m json.tool
```

Expected: `200` response with `"note": "This passage speaks to me because..."`.

- [ ] **Step 6: Verify PATCH rejects oversized notes**

```bash
python -c "print('x' * 3001)" | xargs -I{} curl -s -X PATCH \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"note\": \"$(python -c 'print(\"x\" * 3001)')\"}" \
  http://localhost:8000/v1/bookmarks/<BOOKMARK_ID>
```

Expected: `422` response from Pydantic validation.

- [ ] **Step 7: Verify PATCH rejects wrong owner**

Use a different user's bookmark ID — expected: `404 Bookmark not found`.

- [ ] **Step 8: Verify PATCH clears the note with `null`**

```bash
curl -s -X PATCH \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"note": null}' \
  http://localhost:8000/v1/bookmarks/<BOOKMARK_ID> | python -m json.tool
```

Expected: `200` with `"note": null`.

- [ ] **Step 9: Commit**

```bash
cd ../..
git add services/api/app/routes/bookmarks.py
git commit -m "feat(api): add PATCH /v1/bookmarks/{id} for note updates"
```

---

## Task 4: Frontend API Layer

**Files:**
- Modify: `apps/web/src/lib/api.ts`

**Interfaces:**
- Consumes: `PATCH /v1/bookmarks/{bookmark_id}` from Task 3
- Produces:
  - `Bookmark.note: string | null` — added to existing interface
  - `updateBookmarkNote(token, bookmarkId, note): Promise<Bookmark>` — new export

- [ ] **Step 1: Add `note` to the `Bookmark` interface**

In `apps/web/src/lib/api.ts`, find the `Bookmark` interface (around line 215) and add the `note` field:

```typescript
export interface Bookmark {
  id: string;
  chunk_id: string;
  created_at: string;
  note: string | null;
  chunk: BookmarkChunkInfo | null;
}
```

- [ ] **Step 2: Add `updateBookmarkNote` function**

After the `removeBookmark` function, add:

```typescript
export async function updateBookmarkNote(
  token: string,
  bookmarkId: string,
  note: string | null,
): Promise<Bookmark> {
  const res = await fetch(`${API_URL}/v1/bookmarks/${bookmarkId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(`Failed to update note: ${res.status}`);
  return res.json() as Promise<Bookmark>;
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd apps/web
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd ../..
git add apps/web/src/lib/api.ts
git commit -m "feat(web): add updateBookmarkNote API function and note field to Bookmark type"
```

---

## Task 5: BookmarkCard Note UI

**Files:**
- Modify: `apps/web/src/components/bookmarks/BookmarkCard.tsx`

**Interfaces:**
- Consumes:
  - `Bookmark.note: string | null` from Task 4
  - `updateBookmarkNote(token, bookmarkId, note): Promise<Bookmark>` from Task 4
- Produces:
  - `onNoteUpdated(bookmarkId: string, note: string | null) => void` prop — called after a successful save, so the parent can sync state

- [ ] **Step 1: Replace `BookmarkCard.tsx` with the full implementation**

```typescript
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bookmark as BookmarkIcon, ChevronDown, ChevronUp, Copy, Pencil, Search } from "lucide-react";
import { removeBookmark, updateBookmarkNote, type Bookmark } from "@/lib/api";
import { trackBookmarkDeleted, trackExploreMoreClicked } from "@/lib/analytics";
import { getCollectionMeta } from "@/lib/collections";
import { renderVerseMarkers, stripVerseMarkers } from "@/lib/verse-markers";

const NOTE_MAX = 3000;

interface BookmarkCardProps {
  bookmark: Bookmark;
  token: string | null;
  onRemoved: (bookmarkId: string) => void;
  onNoteUpdated: (bookmarkId: string, note: string | null) => void;
  showToast: (message: string, type?: "success" | "error") => void;
}

export function BookmarkCard({ bookmark, token, onRemoved, onNoteUpdated, showToast }: BookmarkCardProps) {
  const router = useRouter();
  const [noteOpen, setNoteOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftNote, setDraftNote] = useState("");
  const [saving, setSaving] = useState(false);

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
          <BookmarkIcon size={16} />
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
    if (!token) return;
    try {
      await removeBookmark(token, bookmark.id);
      onRemoved(bookmark.id);
      trackBookmarkDeleted({ collection });
    } catch {
      showToast("Couldn't remove. Try again.", "error");
    }
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
          <button
            onClick={handleRemove}
            title="Remove bookmark"
            aria-label="Remove bookmark"
            className="p-1.5 rounded text-sm transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            <BookmarkIcon size={16} className="text-brand-accent" />
          </button>
          <button
            onClick={handleCopy}
            title="Copy passage"
            aria-label="Copy passage"
            className="p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            <Copy size={16} />
          </button>
          <button
            onClick={handleExploreMore}
            title="Explore more like this"
            aria-label="Explore more like this"
            className="p-1.5 rounded text-sm text-brand-muted transition-colors hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            <Search size={16} />
          </button>
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
            <textarea
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
              className="flex items-center gap-1.5 text-xs text-brand-muted hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-brand-accent rounded"
            >
              {noteOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              Note
            </button>
            {noteOpen && (
              <div className="mt-2">
                <p className="text-sm text-brand-primary leading-relaxed whitespace-pre-wrap">
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
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd apps/web
npx tsc --noEmit
```

Expected: errors will appear referencing `onNoteUpdated` missing from callers — that is expected and will be fixed in Task 6.

- [ ] **Step 3: Commit**

```bash
cd ../..
git add apps/web/src/components/bookmarks/BookmarkCard.tsx
git commit -m "feat(web): add inline note UI to BookmarkCard"
```

---

## Task 6: BookmarksPage Integration

**Files:**
- Modify: `apps/web/src/components/bookmarks/BookmarksPage.tsx`

**Interfaces:**
- Consumes:
  - `BookmarkCard` now requires `onNoteUpdated: (bookmarkId: string, note: string | null) => void` prop (from Task 5)
- Produces: fully working Saved Passages page with note feature

- [ ] **Step 1: Add `onNoteUpdated` handler to `BookmarksPage.tsx`**

Replace the entire file with:

```typescript
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAppContext } from "@/components/layout/AppShell";
import { ResultsSkeleton } from "@/components/search/ResultsSkeleton";
import { BookmarkCard } from "./BookmarkCard";
import { getBookmarks, type Bookmark } from "@/lib/api";
import { Toast, useToast } from "@/components/common";

export function BookmarksPage() {
  const { token } = useAppContext();
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const { toast, showToast, dismissToast } = useToast();

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

  function handleNoteUpdated(bookmarkId: string, note: string | null) {
    setBookmarks((prev) =>
      prev.map((b) => (b.id === bookmarkId ? { ...b, note } : b))
    );
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-6 max-w-3xl w-full mx-auto">
        <h1 className="text-2xl font-semibold text-brand-primary mb-6">Saved Passages</h1>

        {loading && <ResultsSkeleton count={3} />}

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
          <div className="space-y-3">
            {bookmarks.map((bookmark) => (
              <BookmarkCard
                key={bookmark.id}
                bookmark={bookmark}
                token={token}
                onRemoved={(id) => setBookmarks((prev) => prev.filter((b) => b.id !== id))}
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
```

- [ ] **Step 2: Verify TypeScript compiles cleanly**

```bash
cd apps/web
npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 3: Run the dev server and test the full flow**

```bash
cd apps/web
npm run dev
```

Open `http://localhost:3000/bookmarks` and verify:

1. **No note state:** Each bookmark card shows "Add note" button at the bottom.
2. **Add note:** Click "Add note" → textarea expands, placeholder visible, autofocused.
3. **Character counter:** Type and watch `N / 3,000` update. At 3,000 chars, counter turns amber and "Character limit reached (3,000 max)" appears; typing is blocked.
4. **Cancel:** Click Cancel → textarea disappears, "Add note" button returns, no change to bookmark.
5. **Save note:** Type a multi-paragraph note, click Save → "Note saved" toast appears, "Add note" is replaced by "Note" toggle.
6. **Collapse/expand:** Click "Note" toggle → note text appears/disappears with chevron toggling.
7. **Edit note:** Expand note, click "Edit" → textarea opens pre-populated with existing note text.
8. **Clear note:** In edit mode, clear all text, click Save → note is removed, "Add note" button returns.
9. **Persist on refresh:** Reload the page — saved note is still there.
10. **Null chunk card:** Ensure the unavailable-passage fallback card still renders without errors.

- [ ] **Step 4: Commit**

```bash
cd ../..
git add apps/web/src/components/bookmarks/BookmarksPage.tsx
git commit -m "feat(web): wire onNoteUpdated into BookmarksPage"
```
