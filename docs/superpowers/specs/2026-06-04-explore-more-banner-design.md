# Explore More — Banner + Full-Content Search

**Date:** 2026-06-04
**Status:** Approved

## Context

The "Explore More" button on ChunkCard, ReaderChunk, and BookmarkCard lets users find passages similar to one they've already found. Currently it truncates the passage to 200 chars before using it as a search query, which hurts retrieval quality because the truncated fragment produces a worse embedding than the complete theological prose. The search bar also fills with raw passage text, which is visually noisy and confusing — it looks like the user typed a long paragraph.

This spec fixes both problems: send the full passage to the backend unchanged, and replace the query bubble with a slim amber banner that shows the passage reference (e.g. "John 3:3–10") instead.

## What Changes

### 1. Full content sent as query — no truncation

Every explore-more path drops the `content.slice(0, 200).replace(/\s+\S*$/, "")` truncation and passes the raw `content` string. The embedding, HyDE, and query expansion steps all benefit from complete theological prose as input.

### 2. `onExploreMore` signature: add `label` param

Wherever `onExploreMore` is a prop or callback, its signature changes from:
```ts
(content: string) => void
```
to:
```ts
(content: string, label: string) => void
```
`label` is the human-readable reference to show in the banner. Each call site computes it the same way it already computes `primaryReference` for display.

### 3. `handleSearch` gains optional `exploreLabel` param

```ts
async function handleSearch(queryOverride?: string, exploreLabel?: string)
```

- When called from an explore path, `exploreLabel` is the reference string → stored in `exploreLabel` state.
- When called from the normal search bar (user typing), `exploreLabel` is `undefined` → clears the state.
- This single mechanism covers all cases without extra cleanup logic.

### 4. `exploreLabel` state in SearchPage

New state: `const [exploreLabel, setExploreLabel] = useState<string | null>(null)`.

Set inside `handleSearch` at the top: `setExploreLabel(exploreLabel ?? null)`.

Cleared on New Search reset (in the `searchKey` effect).

### 5. Banner replaces the query bubble during explore mode

**Suppress** the submitted-query bubble when `exploreLabel !== null`:
```tsx
{submittedQuery && !exploreLabel && (
  <div className="flex justify-end mb-4">…</div>
)}
```

**Add** the banner immediately above `SearchResults` when `exploreLabel` is set:
```tsx
{exploreLabel && (
  <div className="flex items-center gap-2 mb-4 px-1 py-2 rounded-lg
                  bg-brand-accent/10 border border-brand-accent/20">
    <span className="text-brand-accent text-sm">🔍</span>
    <span className="text-sm text-brand-muted">
      Exploring passages related to{" "}
      <span className="text-brand-primary font-medium">{exploreLabel}</span>
    </span>
  </div>
)}
```

The banner disappears naturally when the user submits a new typed query (because `handleSearch` without an `exploreLabel` arg clears the state).

### 6. Search bar stays empty during explore

`handleExploreMore` removes the `setSearchValue(content)` call. The bar shows its placeholder ("Ask a question…") while the explore search runs.

### 7. Reader and Bookmark explore-more: pass `?exploreRef=` URL param

`DocumentReader.handleExploreMore` and `BookmarkCard.handleExploreMore` update their `router.push` calls:
```ts
router.push(
  `/search?explore=${encodeURIComponent(content)}&exploreRef=${encodeURIComponent(label)}`
);
```

`SearchPage` reads `const exploreRef = searchParams.get("exploreRef")` and passes it as the `exploreLabel` arg when auto-submitting the `?explore=` query.

Fallback: if `exploreRef` is absent or empty, `SearchPage` uses a 60-char truncation of `exploreQuery` as the label (covers old links and null-reference edge cases).

## Label Computation Per Call Site

| Call site | Label value |
|---|---|
| `ChunkCard` | `primaryReference` (already computed: `collection === "church-fathers" && reference && document_title ? "${document_title}, ${reference}" : reference ?? document_title`) |
| `ReaderChunk` | `chunk.reference ?? document.title` |
| `BookmarkCard` | `reference ?? document_title` (same as existing `displayReference`) |

## Files Changed

| File | Change summary |
|---|---|
| `apps/web/src/components/search/ChunkCard.tsx` | Pass full `content` + `primaryReference`; update `onExploreMore` call |
| `apps/web/src/components/search/SearchResults.tsx` | Update `onExploreMore` prop type |
| `apps/web/src/components/search/SearchPage.tsx` | `exploreLabel` state; updated `handleSearch` signature; banner render; suppress query bubble; `handleExploreMore` no longer sets `searchValue`; read `?exploreRef=` param |
| `apps/web/src/components/reader/ReaderChunk.tsx` | Pass full `content` + reference label; update `onExploreMore` call and prop type |
| `apps/web/src/components/reader/DocumentReader.tsx` | Update `handleExploreMore` signature; add `?exploreRef=` to URL push |
| `apps/web/src/components/bookmarks/BookmarkCard.tsx` | Pass full `content` + `displayReference`; add `?exploreRef=` to URL push |

## What Does NOT Change

- Backend pipeline — no changes. Full content as query is already valid input.
- `api.ts` — no changes.
- Rate limiting, analytics events, abort/debounce logic — unchanged.
- The 300ms debounce in `handleExploreMore` — unchanged.
- The `?explore=` URL param format — still the full content (existing links remain valid via the fallback label).
