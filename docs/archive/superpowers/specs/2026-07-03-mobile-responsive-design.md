# Mobile-Responsive Layout — Nav Shell + Search Page

**Date:** 2026-07-03
**Status:** Approved
**Scope:** Phase 1 of 2. Covers the app-wide navigation shell (`AppShell`/`Sidebar`) and the Search page. Reader, Bookmarks, Sources, Discover, Settings, and About are explicitly out of scope — a follow-up spec once this pattern is validated.

## Problem

The app has no mobile responsiveness today — only `AboutPage.tsx` uses any Tailwind breakpoint class anywhere in the codebase. The `Sidebar` component is a fixed `w-56` column, always rendered inline by `AppShell` on every authenticated page, bundling branding, the "New Search" action, the search-history list, and page navigation (Sources/Discover/Bookmarks/About/Settings). On a phone-width viewport this consumes the majority of the screen permanently.

## Goals

- Phone-width viewports (<768px) get a usable, native-feeling layout.
- Laptop/tablet viewports (≥768px) are **pixel-identical** to current behavior — zero visual or behavioral change.
- One nav component, one code path — mobile is a responsive state of the existing `Sidebar`, not a parallel implementation.

## Non-goals

- No redesign of desktop layout or information architecture (nav stays bundled with history, as today — the current top/scroll-middle/pinned-bottom regions already resolve the "dynamic history vs. static nav" tension without needing a second nav surface).
- No changes to `AppContext`'s public interface.
- No changes to any page besides Search in this phase.

## Governing technical principle: `max-md:` only

Tailwind v4 supports `max-*` variants (`max-md:flex-col`, `max-md:hidden`, etc.), which apply *only below* a breakpoint. Every mobile-specific change in this spec is additive via `max-md:` classes layered onto existing markup. **No existing unprefixed class is removed or edited.** This is what makes "won't ruin, change, or clash with anything current" a structural guarantee rather than a promise to be careful: at ≥768px, `max-md:*` rules simply don't apply, so current desktop CSS is the only CSS in effect, unchanged.

Breakpoint: Tailwind's `md` (768px). Chosen because it's comfortably above all common phone widths (≤430px) and matches typical small-tablet/laptop boundaries, and because it's the one breakpoint used consistently across both the shell and Search sections below — a single mental model for "mobile" throughout this phase.

## Section 1 — Responsive Nav Shell

**Components touched:** `AppShell.tsx`, `Sidebar.tsx` (styling only), one new `MobileTopBar.tsx`.

**Desktop (≥768px):** unchanged. `Sidebar` renders inline, static, always visible, exactly as today.

**Mobile (<768px):**
- `Sidebar`'s `<aside>` gains `max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:w-72 max-md:transition-transform max-md:duration-200` plus a state-driven `max-md:-translate-x-full` (closed) / `max-md:translate-x-0` (open). Internal JSX (brand, new-search button, history list, nav links) is untouched.
- A new `MobileTopBar` (~52px, `md:hidden`) renders inside `<main>`, above `{children}`, as a `shrink-0` element — it doesn't compete with the scrollable content region below it. Contains a hamburger button and the wordmark.
- A backdrop (`max-md:fixed max-md:inset-0 max-md:bg-black/50 max-md:z-30`) renders behind the drawer when open; clicking it, pressing Escape, or clicking any link/history item inside the drawer closes it.
- `mobileNavOpen` boolean lives as local state in `AppShell` (not added to `AppContextValue` — only `Sidebar` and `MobileTopBar` need it, passed as props). Closed by default.
- Body scroll is locked (`document.body.style.overflow = "hidden"`) while the drawer is open on mobile, restored on close.
- Focus handling: opening moves focus into the drawer; Tab/Shift+Tab are trapped within it; closing returns focus to the hamburger button. Hamburger button carries `aria-expanded`.
- A `matchMedia("(min-width: 768px)")` listener force-closes `mobileNavOpen` if the viewport crosses into desktop width while open (e.g., rotating a tablet or resizing a window) — prevents stale drawer state.

## Section 2 — Search Page Mobile Adjustments

All changes below are `max-md:` additions only; several components (`CollectionToggles`, `ResultFilterBar`) already use `flex-wrap` and need no change at all.

| Component | Current risk on phone width | Fix |
|---|---|---|
| `BottomBar.tsx` pre-search row | `CollectionToggles` (flex-wrap, grows) + `QuotaControl` (shrink-0) fight for space in one `justify-between` row — wraps awkwardly | `max-md:flex-col max-md:items-stretch max-md:gap-2` on the row so they stack |
| `ChunkCard.tsx` header | "Relevance Score:" label + reference/title text compete for width | `max-md:hidden` on the label text; percentage chip stays visible |
| `ChunkCard.tsx` expanded action row | 2 icon buttons + 2 text buttons ("Read More", "Query more sources like this") in one `justify-between` row can overflow/compress | `max-md:flex-wrap`; "Query more sources like this" swaps to a shorter "Explore more" label below 768px |
| `SearchPage.tsx` query bubble | `max-w-[70%]` is ≈260px on a 375px phone — cramped for longer questions | `max-md:max-w-[85%]` |

**Verify-only, no planned change (already fluid or low-risk):**
- `LoadingAnimation` — confirmed it measures its own container via `getBoundingClientRect()`, no fixed pixel dimensions. Already mobile-safe.
- `TranslationSelector` popover (`absolute`, `min-w-[160px]`) — anchored to the Bible pill; check visually during implementation for edge-of-screen clipping, adjust only if actually observed.
- `SearchBar` — textarea (`flex-1`) + button (`shrink-0`) already degrade gracefully; no change planned.

## Testing / verification plan

- Manual check at 375×667 (iPhone SE-class, smallest common target), 390×844 (iPhone standard), and 768/1024/1440 (tablet/laptop breakpoints either side of `md`) via browser dev tools device toolbar.
- Confirm zero visual diff at ≥768px against current `master` (side-by-side screenshot comparison of Search page and one other page, e.g. Bookmarks, to confirm the shell doesn't regress a page outside this phase's scope).
- Drawer: open/close via hamburger, backdrop tap, Escape; tab-trap works; auto-closes on link/history selection; auto-closes if resized past 768px while open.
- Search page: run an actual search on a simulated phone viewport, expand a chunk card, confirm action row doesn't overflow.

## Out of scope (next spec)

Reader, Bookmarks, Sources, Discover, Settings, About — each gets its own mobile pass once this shell pattern is in place and proven.
