# Task 23 — Search Page Bottom Bar
**Date:** 2026-05-30
**Branch:** `feature/v2-rag`

---

## Scope

Build the fixed bottom bar for the `/search` page: collection toggles, translation selector, per-source quota control, and search input. Also add "Code of Canon Law" as a new collection across all infrastructure layers.

---

## 1. Canon Law Infrastructure Changes

These changes must land before or alongside the frontend work.

### 1a. Database — Migration 0007

New file: `supabase/migrations/0007_add_canon_law_collection.sql`

```sql
-- Drop old CHECK constraint (auto-named by Postgres)
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_collection_check;

-- Add new constraint including canon-law
ALTER TABLE documents
  ADD CONSTRAINT documents_collection_check
  CHECK (collection IN ('bible','catechism','church-fathers','encyclicals','canon-law','saints'));

-- Update default for future rows (existing rows unaffected)
ALTER TABLE user_preferences
  ALTER COLUMN default_collections
  SET DEFAULT '{bible,catechism,church-fathers,encyclicals,canon-law,saints}';
```

### 1b. Backend — `routes/search.py`
Line 26: add `'canon-law'` to `_VALID_COLLECTIONS`.

### 1c. Backend — `routes/preferences.py`
- Line 14: add `'canon-law'` to `_VALID_COLLECTIONS`
- Line 19: add `'canon-law'` to `_DEFAULT_PREFERENCES.default_collections`

### 1d. Backend — `rag/pipeline.py`
Line 38: add `'canon-law'` to `VALID_COLLECTIONS`.

---

## 2. Frontend Components

All files created in `apps/web/src/components/search/`.

### 2a. CollectionToggles.tsx

Six pills in order: Bible ▾, Catechism, Church Fathers, Encyclicals, Canon Law, Saints.

**Pill states:**
- Active: `bg-brand-accent text-brand-bg`
- Inactive: `bg-brand-surface text-brand-muted border border-brand-surface`

**Bible pill** has a `▾` chevron that opens `TranslationSelector` as a sub-dropdown above the pill. The dropdown closes when clicking outside or selecting a translation. The `translationOpen: boolean` state is local to `CollectionToggles` — it is not a prop.

**Reads from:** `useAppContext()` → `preferences.default_collections` (initial toggle state) and `preferences.preferred_translation` (passed to TranslationSelector).

**Writes via:** 500ms debounced call to `updatePreferences(token, { default_collections })` on every toggle change. Optimistic update: local state updates immediately, debounced API call syncs after.

**Props:**
```ts
interface CollectionTogglesProps {
  activeCollections: string[];
  onToggle: (collection: string) => void;
  translation: string;
  onTranslationChange: (t: string) => void;
}
```

### 2b. TranslationSelector.tsx

Dropdown that opens **upward** (since the bar is at the bottom of the viewport) with `bottom: calc(100% + 6px)` positioning relative to the Bible pill wrapper.

Options: `CPDV` (default), `Douay-Rheims`.

Closes on outside click via `useEffect` that attaches a `mousedown` listener on `document`. Uses a `ref` on the container to distinguish inside vs outside clicks.

**Props:**
```ts
interface TranslationSelectorProps {
  value: string;
  onChange: (translation: string) => void;
  onClose: () => void;
}
```

### 2c. QuotaControl.tsx

Segmented `[3 | 4 | 5]` control. Active segment: `bg-brand-accent text-brand-bg font-semibold`. Inactive: `bg-brand-surface text-brand-muted`.

Default value comes from `preferences.default_quota` (via props from parent). Calls `updatePreferences(token, { default_quota })` on change with 500ms debounce.

**Props:**
```ts
interface QuotaControlProps {
  value: number;
  onChange: (quota: number) => void;
}
```

### 2d. SearchBar.tsx

Controlled `<input>` + Search `<button>`.

- `Enter` key submits (no Shift+Enter handling needed — single-line input)
- Disabled during `loading` prop = true; button shows "Searching…" with spinner
- When all collections are off (detected via `disabled` prop from parent): input shows placeholder "Select at least one source to search." and button is disabled with `title` tooltip
- Input: `bg-brand-surface border border-brand-surface rounded-lg` focus ring in accent color

**Props:**
```ts
interface SearchBarProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  disabled: boolean; // true when no collections active
}
```

### 2e. BottomBar.tsx

Wrapper component. Two rows:
- Row 1: `<CollectionToggles>` + `<QuotaControl>` (flex, items-center, space-between)
- Row 2: `<SearchBar>`

Positioned as the natural bottom element of the search page's flex column — **not** CSS `position: fixed`. The search page will be a flex column where the results region takes `flex-1 overflow-y-auto` and BottomBar sits below it.

Has a `border-t border-brand-surface` separator, `bg-brand-bg` background, `p-3 pb-4` padding.

**Props:**
```ts
interface BottomBarProps {
  activeCollections: string[];
  onToggleCollection: (c: string) => void;
  translation: string;
  onTranslationChange: (t: string) => void;
  quota: number;
  onQuotaChange: (q: number) => void;
  searchValue: string;
  onSearchChange: (v: string) => void;
  onSearch: () => void;
  loading: boolean;
}
```

---

## 3. Collection Metadata (for ChunkCard color coding, Task 25)

| Collection | Key | Pill label | Color |
|---|---|---|---|
| Bible | `bible` | 📖 Bible ▾ | `#4caf50` |
| Catechism | `catechism` | ⛪ Catechism | `#4a6fa5` |
| Church Fathers | `church-fathers` | ✝ Church Fathers | `#7c6fa5` |
| Encyclicals | `encyclicals` | 📜 Encyclicals | `#b5892a` |
| Code of Canon Law | `canon-law` | ⚖️ Canon Law | `#9e4a4a` |
| Saints | `saints` | 👼 Saints | `#4a9a8a` |

---

## 4. Debounce Implementation

Both `CollectionToggles` and `QuotaControl` use a shared debounce pattern:
- Local state updates immediately (optimistic)
- `useEffect` with cleanup fires `updatePreferences` after 500ms
- If component unmounts before the timeout fires, cleanup cancels it (no stale API call)

Pattern:
```ts
useEffect(() => {
  const timer = setTimeout(() => {
    updatePreferences(token, { ... }).catch(() => {});
  }, 500);
  return () => clearTimeout(timer);
}, [dependency]);
```

---

## 5. Validation

`BottomBar` computes `noCollections = activeCollections.length === 0` and passes `disabled={noCollections}` to `SearchBar`.

---

## 6. Out of Scope for Task 23

- SearchPage.tsx state orchestration (Task 24)
- Search results rendering (Task 25)
- EmptyState suggested queries (Task 24)
- Any route-level page file (Task 29)
