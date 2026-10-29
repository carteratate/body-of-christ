# Reader Rework — Professional Document Reading & Navigation

**Date:** 2026-06-13
**Status:** Approved (design)
**Depends on:** [Shared Contract](2026-06-13-passage-contract-design.md)

## 1. Goal

Replace the current chunk-window reader with a clean, professional reading experience — "like reading the
Bible in a Bible app" — for **every** collection. Reading must feel continuous and uncluttered, with
intuitive navigation to an exact verse / article / paragraph, and clear paths into the reader from search
results and from the Sources list.

### Problems with today's reader (`apps/web/src/components/reader/`)
- Renders retrieval **search chunks**: boxed cards, `[breadcrumb]` headers, `(1/3)` split suffixes, and
  visible overlap repetition.
- Paginates by a ±10 **position window** with Prev/Next; no chapter/verse concept.
- Sources list is not clickable; church-fathers rows have synthetic IDs that cannot open a reader.

## 2. What the reader consumes

The reader reads **only clean canonical passages** via the contract's API (no Qdrant, no search chunks):
- `GET /v1/documents/{id}/toc` → chapter list for the pickers + Contents drawer.
- `GET /v1/documents/{id}/reader?anchor=…|?chapter=…` → one chapter section of ordered passages, with
  `prev_chapter_key`/`next_chapter_key` and `highlight_anchor`.

## 3. Navigation model — hybrid continuous scroll (approved)

- **One chapter = one section.** The reader loads a chapter's passages and renders them as continuous,
  styled prose (serif body, chapter heading, inline verse/paragraph ordinals from `unit_label`).
- **Smooth continuous scroll.** Reaching the end of a chapter lazily appends the next chapter
  (`next_chapter_key`); scrolling up prepends the previous one. No mandatory Prev/Next tapping.
- **Pickers, top-left.** `☰ Contents` + **Book/Work ▾** + **Chapter ▾**. They **jump** anywhere and they
  **track** scroll position — when a chapter heading crosses the top of the viewport, the pickers update to
  that chapter (via an IntersectionObserver on chapter headings).
- **Deep-link.** Opening with `?anchor=` loads that chapter, scrolls the target passage into view, and
  highlights it (gold). Highlight clears on further navigation.
- **Contents drawer.** Built from the TOC; collapsible; current chapter marked; click to jump.

## 4. Entry points into the reader

- **Read More** (search `ChunkCard`): navigates to `/reader/{document_id}?anchor={anchor}` using the
  `anchor` now present on the search result. Opens at the exact passage. (Replaces today's `?chunk_id=`.)
- **Sources list** (`SourcesPage`): every row is clickable.
  - Non-Bible row → `/reader/{document_id}` (opens at first chapter).
  - **Bible** translation row → expands **inline to a book grid** (73 books); clicking a book →
    `/reader/{book_document_id}` at chapter 1. (Approved option A.)
- **Reader internal**: pickers and Contents drawer navigate within/under the same document; the Book picker
  can switch between books of the same Bible translation (sibling documents).

## 5. Frontend components (`apps/web/src/components/reader/`)

Rewrite the reader package:

| Component | Role |
|---|---|
| `DocumentReader.tsx` | Orchestrator: fetch TOC + initial chapter, manage the scroll buffer (ordered list of loaded chapters), lazy prev/next loading, deep-link highlight, picker state. |
| `ReaderChrome.tsx` | Sticky top bar: back, ☰ Contents toggle, Book/Work picker, Chapter picker, translation/collection label. Replaces `ReaderToolbar.tsx`. |
| `ContentsDrawer.tsx` | TOC list, current-chapter tracking, jump. |
| `ChapterSection.tsx` | Renders one chapter: heading + ordered passages as continuous prose; exposes the heading node for the IntersectionObserver. Replaces the boxed `ReaderChunk.tsx`. |
| `Passage.tsx` | One passage: inline `unit_label` ordinal + clean `content`; hosts per-passage actions (bookmark, copy, "Query more like this") on hover/selection — not as a permanent boxed toolbar. |
| `BookPicker` / `ChapterPicker` | Dropdowns driven by TOC (+ sibling-book list for Bible). |

- **Typography is collection-aware** but consistent: serif reading body, generous line-height, max reading
  width, Sacred Night tokens (no hardcoded hex; CLAUDE.md §9). Per-collection presentation in §6.
- API client (`apps/web/src/lib/api.ts`): replace `getReader` with `getReaderChapter(token, docId, {anchor?
  , chapter?})` and add `getToc(token, docId)`; update `ReaderResponse` types to the contract shapes.
  `streamSearch`/`getSources` types gain `anchor` / real ids.

## 6. Per-collection reader presentation

- **Bible** — one **chapter** shown at a time (the section); within it, passages follow the source's
  **pericope/heading structure** (not verse-by-verse). Pericope titles render as sub-headings; verse numbers
  render as inline superscripts; the Book picker lists the translation's books; deuterocanonical/Psalms read
  naturally per chapter.
- **Summa** — chapter section = one Article; passages are its parts with `unit_label` headings
  (`Objection 1`, `On the contrary`, `I answer that`, `Reply to Objection 1`); clean expanded references
  (`Summa Theologiae, I-II, Q. 68, A. 3`). (Cleaning/splitting in the pipeline spec.)
- **Catechism** — paragraph passages with CCC `§` numbers as `unit_label`; structural headers become
  `chapter_label`, not stray passages.
- **Encyclicals / Councils / Canon-law / Church-fathers / Medieval** — section/chapter/canon headings as
  `chapter_label`, clean prose, Title-cased headings, footnote markers stripped.

## 7. States & behaviors

- **Loading**: skeleton lines for the initial chapter; subtle inline loader when appending a chapter.
- **Deep-link miss** (anchor not found): fall back to first chapter, no highlight, non-blocking notice.
- **404 / error / empty**: existing patterns (back link, muted message).
- **Bookmarks / copy / explore**: operate at passage granularity; bookmark stores the passage `id`
  (= chunk id), copy yields clean text + clean citation, "Query more like this" reuses the existing
  `/search?explore=` flow with the passage content + reference.
- **Analytics**: keep `trackDocumentOpened` (source: `chunk_card` | `sources` | `reader_nav`),
  `trackReaderNavigation` (direction: next/prev/jump/picker).

## 8. Out of scope (this spec)
- Cross-document "next work" continuation.
- Search-result ranking changes (separate concern).
- Offline/caching, font-size controls (possible later).
