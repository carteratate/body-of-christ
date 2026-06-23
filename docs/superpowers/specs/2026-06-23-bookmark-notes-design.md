# Bookmark Notes — Design Spec

**Date:** 2026-06-23
**Status:** Approved

---

## Overview

Allow authenticated users to attach a personal note to each saved passage (bookmark). One note per bookmark. Notes are multi-paragraph journal-style entries, capped at 3,000 characters. Notes are private to the user who wrote them.

---

## Data Model

### Migration: `0016_bookmarks_add_note.sql`

```sql
ALTER TABLE bookmarks
  ADD COLUMN note text CHECK (char_length(note) <= 3000);
```

- Nullable — existing bookmarks get `NULL` (no note).
- RLS policy already on `bookmarks` (`auth.uid() = user_id`) covers this column automatically.
- The DB-level CHECK constraint is defense-in-depth; Pydantic is the primary enforcement layer.

---

## API

### Updated `GET /v1/bookmarks`

- Adds `b.note` to the SELECT. No new join — the note is returned on every bookmark in the existing list response.
- `BookmarkResponse` gains: `note: Optional[str] = None`

### New `PATCH /v1/bookmarks/{bookmark_id}`

**Request:**
```json
{ "note": "My reflection..." }
```
- `note` may be a string (1–3,000 chars) or `null` (clears the note).
- Pydantic model: `note: Optional[str] = Field(None, max_length=3000)` — returns 422 before any DB interaction if violated.

**Authorization:** `WHERE id = $1 AND user_id = $2` on both the UPDATE and the response SELECT — ownership enforced at the query level, not application logic alone.

**Response:** `200` with the full updated `BookmarkResponse` (including `note`).

**Cache:** `_invalidate_bookmarks(user.user_id)` called on every successful PATCH.

**Rate limiting:** The PATCH endpoint is covered by the existing per-user rate limiter (same pattern as other write routes).

**FastAPI body parsing:** Uses a typed Pydantic body parameter — FastAPI rejects non-JSON bodies by default. No raw `Request` body parsing.

### Frontend: `api.ts`

- `Bookmark` interface gains: `note: string | null`
- New function: `updateBookmarkNote(token: string, bookmarkId: string, note: string | null): Promise<Bookmark>`

---

## Frontend Components

### `BookmarkCard.tsx`

New local state:
- `noteOpen: boolean` — controls collapse/expand of an existing note (default `false`)
- `editing: boolean` — controls textarea visibility
- `draftNote: string` — textarea value during edit
- `saving: boolean` — disables Save button during async call

#### Bottom section (below passage text), behavior by state:

**No note, not editing:**
- Subtle "Add note" button (pencil icon + label, `text-brand-muted`).
- Click → `editing = true`, `draftNote = ""`, textarea focused.

**Note exists, not editing:**
- A toggle row: chevron icon + "Note" label (`text-brand-muted`). Clicking toggles `noteOpen`.
- When `noteOpen = true`: note text renders in a styled read-only block (`text-sm text-brand-primary whitespace-pre-wrap`), followed by an "Edit" button.
- Click "Edit" → `editing = true`, `draftNote = existingNote`.

**Editing (add or edit):**
- `<textarea>` expands in place, `min-h-[100px] resize-y`, pre-populated with `draftNote`.
- `maxLength={3000}` — browser blocks input past the limit.
- Live character counter below textarea: `"{count} / 3,000"`.
  - Counter color: `text-brand-muted` normally; switches to `text-brand-accent` (amber) at 3,000.
  - At 3,000 characters, an inline message appears: `"Character limit reached (3,000 max)"`.
- "Save" and "Cancel" buttons.
  - Save: calls `updateBookmarkNote`, sets `saving = true` during the call, updates note in parent state via `onNoteUpdated`, exits editing.
  - Cancel: resets `draftNote`, sets `editing = false`.

#### Security invariant
Note content MUST render via JSX text interpolation (`{note}`) only. `dangerouslySetInnerHTML` is prohibited for note display anywhere in the component tree.

### `BookmarksPage.tsx`

- `BookmarkCard` receives a new `onNoteUpdated(bookmarkId: string, note: string | null) => void` prop.
- Handler patches the matching bookmark's `note` field in local state — no refetch needed.

---

## Character Limit — Enforcement Layers

| Layer | Mechanism | Role |
|---|---|---|
| Browser | `maxLength={3000}` on textarea | UX — prevents typing past limit |
| UX feedback | Counter + inline message at 3,000 | UX — communicates the limit clearly |
| Pydantic | `Field(max_length=3000)` on `note` | Primary security enforcement — 422 on violation |
| Database | `CHECK (char_length(note) <= 3000)` | Defense-in-depth backstop |

---

## Out of Scope

- Notes are not searchable (no FTS index, no search endpoint change).
- No note history / versioning.
- No note export.
- No markdown rendering — plain text only.
