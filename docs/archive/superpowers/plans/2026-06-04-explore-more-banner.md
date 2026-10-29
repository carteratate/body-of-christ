# Explore More — Banner + Full-Content Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the 200-char truncation from every Explore More path, pass the full passage content to the backend, and replace the raw-text query bubble with a slim amber banner showing the passage reference.

**Architecture:** `onExploreMore` prop gains a second `label` string param (the human-readable reference). `handleSearch` in SearchPage gains an optional `exploreLabel` param that sets/clears new `exploreLabel` state. A banner renders when `exploreLabel !== null`; the query bubble is suppressed in the same condition. Reader/bookmark paths thread the label through a new `?exploreRef=` URL param.

**Tech Stack:** Next.js 15, React, TypeScript. No backend changes. No new dependencies.

---

## File Map

| File | Change |
|---|---|
| `apps/web/src/components/search/ChunkCard.tsx` | Remove truncation; pass full content + `primaryReference` as label |
| `apps/web/src/components/search/SearchResults.tsx` | Update `onExploreMore` prop type (pass-through) |
| `apps/web/src/components/search/SearchPage.tsx` | `exploreLabel` state; `handleSearch` signature; banner; suppress bubble; no `setSearchValue` in explore handler; read `?exploreRef=` |
| `apps/web/src/components/reader/ReaderChunk.tsx` | Remove truncation; pass full content + reference label |
| `apps/web/src/components/reader/DocumentReader.tsx` | Update `handleExploreMore` signature; add `?exploreRef=` to URL |
| `apps/web/src/components/bookmarks/BookmarkCard.tsx` | Remove truncation; add `?exploreRef=` to URL |

---

### Task 1: ChunkCard — remove truncation, pass label

**Files:**
- Modify: `apps/web/src/components/search/ChunkCard.tsx`

- [ ] **Step 1: Update the `onExploreMore` prop type and `handleExploreMore` body**

In `ChunkCard.tsx`, find the `ChunkCardProps` interface and `handleExploreMore` function. Make these two changes:

```tsx
// ChunkCardProps — update the prop type
interface ChunkCardProps {
  result: ChunkResult;
  index: number;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string, label: string) => void;  // was: (content: string) => void
}
```

```tsx
// handleExploreMore — remove truncation, pass primaryReference as label
function handleExploreMore() {
  trackExploreMoreClicked({ collection, source: "chunk_card" });
  onExploreMore(content, primaryReference ?? "");
}
```

`primaryReference` is already computed earlier in the same function body:
```ts
const primaryReference =
  collection === "church-fathers" && reference && document_title
    ? `${document_title}, ${reference}`
    : reference ?? document_title;
```

- [ ] **Step 2: Verify TypeScript catches the type mismatch upstream**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | grep -E "onExploreMore|ChunkCard|SearchResults|SearchPage"
```

Expected: errors referencing `onExploreMore` in `SearchResults.tsx` and `SearchPage.tsx` — these are the next tasks. No other errors from this file.

---

### Task 2: SearchResults — update prop type

**Files:**
- Modify: `apps/web/src/components/search/SearchResults.tsx`

- [ ] **Step 1: Update the `onExploreMore` prop type**

In `SearchResults.tsx`, find `SearchResultsProps` and update the type:

```tsx
interface SearchResultsProps {
  results: ChunkResult[];
  loading: boolean;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string, label: string) => void;  // was: (content: string) => void
  phase?: "searching" | "ranking" | null;
  collections?: string[];
}
```

The JSX pass-through `onExploreMore={onExploreMore}` on `ChunkCard` is unchanged.

- [ ] **Step 2: Verify TypeScript**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | grep -E "onExploreMore|SearchResults"
```

Expected: only remaining errors in `SearchPage.tsx`.

---

### Task 3: SearchPage — state, banner, and explore logic

**Files:**
- Modify: `apps/web/src/components/search/SearchPage.tsx`

This task has several sub-changes to the same file. Apply them in order.

- [ ] **Step 1: Add `exploreLabel` state and read `?exploreRef=` param**

After the existing `const [searchPhase, ...]` line, add:

```tsx
const [exploreLabel, setExploreLabel] = useState<string | null>(null);
```

After `const exploreQuery = searchParams.get("explore");`, add:

```tsx
const exploreRef = searchParams.get("exploreRef");
```

- [ ] **Step 2: Update `handleSearch` to accept and set `exploreLabel`**

Change the function signature and add `setExploreLabel` near the top of the function body:

```tsx
const handleSearch = useCallback(
  async (queryOverride?: string, newExploreLabel?: string) => {
    const query = queryOverride ?? searchValue;
    if (loading || activeCollections.length === 0 || !query.trim()) return;
    const currentToken = tokenRef.current;
    if (!currentToken) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const pid = pendingIdRef.current ?? crypto.randomUUID();
    pendingIdRef.current = pid;
    setPendingSearch(pid, query);
    setActiveSearchId(pid);

    setLoading(true);
    setSearchPhase(null);
    setError(null);
    setRateLimitRetryAfter(null);
    setRateLimitType("per_minute");
    setSubmittedQuery(query);
    setSearchValue("");
    setResults([]);
    setExploreLabel(newExploreLabel ?? null);  // ← new line

    try {
      await streamSearch(
        // ... rest of body unchanged
```

- [ ] **Step 3: Update `handleExploreMore` — no `setSearchValue`, pass label**

Replace the existing `handleExploreMore`:

```tsx
const handleExploreMore = useCallback((content: string, label: string) => {
  if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
  exploreTimerRef.current = setTimeout(() => {
    handleSearch(content, label);
  }, 300);
}, [handleSearch]);
```

- [ ] **Step 4: Update the `?explore=` auto-submit effect to pass the label**

Replace the existing explore effect:

```tsx
useEffect(() => {
  if (!exploreQuery || !token) return;
  if (exploredForQuery.current === exploreQuery) return;
  exploredForQuery.current = exploreQuery;
  const label = exploreRef?.trim()
    || (exploreQuery.slice(0, 60).replace(/\s+\S*$/, "") + (exploreQuery.length > 60 ? "…" : ""));
  const timer = setTimeout(() => {
    handleSearch(exploreQuery, label);
  }, 100);
  return () => clearTimeout(timer);
}, [exploreQuery, exploreRef, token, handleSearch]);
```

Note: `setSearchValue(exploreQuery)` is removed — the bar stays empty during explore mode.

- [ ] **Step 5: Clear `exploreLabel` in the New Search reset effect**

In the effect watching `searchKey`, add `setExploreLabel(null)` alongside the other state resets:

```tsx
useEffect(() => {
  if (prevSearchKey.current === searchKey) return;
  prevSearchKey.current = searchKey;
  abortRef.current?.abort();
  if (exploreTimerRef.current) clearTimeout(exploreTimerRef.current);
  setResults([]);
  setSubmittedQuery(null);
  setSearchId(null);
  setError(null);
  setLoading(false);
  setSearchValue("");
  setSearchPhase(null);
  setRateLimitRetryAfter(null);
  setExploreLabel(null);           // ← new line
  restoredForId.current = null;
  exploredForQuery.current = null;
  activatePendingSlot();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [searchKey]);
```

- [ ] **Step 6: Update the render — suppress query bubble, add banner**

In the JSX, find the submitted-query bubble and add the `!exploreLabel` guard:

```tsx
{submittedQuery && !exploreLabel && (
  <div className="flex justify-end mb-4">
    <div className="max-w-[70%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
      {submittedQuery}
    </div>
  </div>
)}

{exploreLabel && (
  <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg bg-brand-accent/10 border border-brand-accent/20">
    <span className="text-brand-accent text-sm">🔍</span>
    <span className="text-sm text-brand-muted">
      Exploring passages related to{" "}
      <span className="text-brand-primary font-medium">{exploreLabel}</span>
    </span>
  </div>
)}
```

- [ ] **Step 7: Verify TypeScript clean**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors related to these files. Fix any that appear before continuing.

- [ ] **Step 8: Commit tasks 1–3**

```bash
git add apps/web/src/components/search/ChunkCard.tsx \
        apps/web/src/components/search/SearchResults.tsx \
        apps/web/src/components/search/SearchPage.tsx
git commit -m "feat(search): explore more — full content query + reference banner"
```

---

### Task 4: ReaderChunk — remove truncation, pass label

**Files:**
- Modify: `apps/web/src/components/reader/ReaderChunk.tsx`

- [ ] **Step 1: Update `onExploreMore` prop type and `handleExploreMore` body**

In `ReaderChunkProps`:

```tsx
interface ReaderChunkProps {
  chunk: ReaderChunkType;
  document: DocumentInfo;
  isOrigin: boolean;
  token: string;
  onExploreMore: (content: string, label: string) => void;  // was: (content: string) => void
}
```

Replace `handleExploreMore`:

```tsx
function handleExploreMore() {
  const label = chunk.reference ?? document.title;
  trackExploreMoreClicked({ collection: document.collection, source: "reader" });
  onExploreMore(chunk.content, label);
}
```

---

### Task 5: DocumentReader — update signature, add `?exploreRef=`

**Files:**
- Modify: `apps/web/src/components/reader/DocumentReader.tsx`

- [ ] **Step 1: Update `handleExploreMore`**

Replace the function (line ~103):

```tsx
function handleExploreMore(content: string, label: string) {
  router.push(
    `/search?explore=${encodeURIComponent(content)}&exploreRef=${encodeURIComponent(label)}`
  );
}
```

- [ ] **Step 2: Verify TypeScript clean**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit tasks 4–5**

```bash
git add apps/web/src/components/reader/ReaderChunk.tsx \
        apps/web/src/components/reader/DocumentReader.tsx
git commit -m "feat(reader): explore more — full content + exploreRef URL param"
```

---

### Task 6: BookmarkCard — remove truncation, add `?exploreRef=`

**Files:**
- Modify: `apps/web/src/components/bookmarks/BookmarkCard.tsx`

- [ ] **Step 1: Update `handleExploreMore`**

Replace the function:

```tsx
function handleExploreMore() {
  trackExploreMoreClicked({ collection, source: "chunk_card" });
  router.push(
    `/search?explore=${encodeURIComponent(content)}&exploreRef=${encodeURIComponent(displayReference ?? "")}`
  );
}
```

`displayReference` is already computed as `reference ?? document_title` earlier in the component.

- [ ] **Step 2: Verify TypeScript fully clean**

```bash
cd apps/web && npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/bookmarks/BookmarkCard.tsx
git commit -m "feat(bookmarks): explore more — full content + exploreRef URL param"
```

---

### Task 7: Manual verification

- [ ] **Step 1: Start the dev server**

```bash
cd apps/web && npm run dev
```

- [ ] **Step 2: Verify search-page explore**

1. Run a search and wait for results with explanations
2. Click "🔍 Explore more" on any result
3. Confirm: search bar stays empty (no passage text visible)
4. Confirm: amber banner appears above results: "🔍 Exploring passages related to [reference]"
5. Confirm: no query bubble (the rounded speech-bubble showing what was typed)
6. Type a new query in the bar and submit → confirm: banner disappears, normal query bubble appears

- [ ] **Step 3: Verify reader explore**

1. From a search result, click "Read More" to open the reader
2. Click "🔍 Explore more" on any chunk
3. Confirm: navigates to `/search?explore=...&exploreRef=...` (check browser URL)
4. Confirm: amber banner shows the correct reference

- [ ] **Step 4: Verify bookmark explore**

1. Open `/bookmarks`
2. Click the 🔍 button on any bookmark
3. Confirm: navigates to `/search?explore=...&exploreRef=...`
4. Confirm: amber banner shows the reference

- [ ] **Step 5: Verify New Search clears explore mode**

1. Run an explore search (banner visible)
2. Click "+ New Search" in the sidebar
3. Confirm: banner gone, empty state shows normally
