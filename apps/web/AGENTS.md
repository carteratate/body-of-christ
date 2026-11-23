<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# apps/web — frontend rules

Repo-wide invariants live in `/CLAUDE.md` at the root. Read it. This file covers only
what bites you inside `apps/web`, and points at the root sections that own each rule.

## Networking

- **Never call the API host from the browser.** Every request goes through the Vercel
  proxy at `src/app/v1/[...path]/route.ts`, which adds `x-internal-secret` server-side.
- **`const API_URL = ""` in `src/lib/api.ts` is correct.** The empty string forces
  relative `/v1/...` paths into the proxy. Do not "fix" it to read an env var.
- **`NEXT_PUBLIC_API_URL` does not route anything.** It is read only by
  `next.config.ts`, for the CSP `connect-src` header.
- No database SDK in the frontend, ever. (Root §1, §16)

## The three modules that own behavior

Reach for these before writing new state handling — each is the single owner of its
concern, and duplicating it in a component is the usual way this codebase regresses.

| Concern | Owner | Don't |
|---|---|---|
| SSE decoding | `src/lib/search-stream.ts` | Add a second decoder, or parse events in a component. Add a new event field here **once**. |
| Search + restore lifecycle | `src/lib/search-experience/` | Put AbortControllers, run generations, stream buffers, terminal flags, or animation timers in `SearchPage.tsx`. |
| Draft quota/collection rules, and genre/issuer selections (5.1a) | `src/lib/search-draft.ts` | Re-derive focused eligibility from a raw quota int. |
| Collection keys, old and new (5.1b) | `src/lib/collections.ts` (`canonicalCollectionKey`, `getCollectionMeta`), `src/lib/collection-scopes.ts` (`canonicalSearchFilters`) | Compare a stored collection key (a bookmark, a document, a saved search) without translating it first: until 5.1b.3 rewrites them, stored keys are old (`encyclicals`, `canon-law`, `medieval`). |

(Root §12, §14, §18)

## Shells and routes

`src/components/layout/AuthenticatedRouteShell.tsx` picks between `AppShell`
(authenticated) and `GuestShell` by matching the pathname against its own
`AUTHENTICATED_ROUTES` list. **A new authenticated route must be added to that list or
it silently renders in the guest shell.**

Authenticated pages live at the bare path; the guest mirror is a sibling under
`/guest/` or `/search/guest`. They share components via an `isGuest` prop rather than
forking — update both together. (Root §10, §11, §13)

## Navigation feedback

Every route is dynamic, so a click shows the destination's `loading.tsx` at once only
if that route was prefetched. For links in lists and cards use `IntentLink`
(`src/components/common/NavPending.tsx`): it prefetches on hover or keyboard focus,
never on sight (a viewport prefetch per row is a middleware run and server render each)
and **never on press** — a prefetch still in flight when the click lands makes that
navigation slower than none (measured in `src/lib/useIntentPrefetch.ts`). Put
same-tab-only side effects in `onNavigate`, which a cmd/ctrl-click never calls. A
navigation that must stay a button uses `usePendingNavigation` and renders
`NavPendingBar`.

## Styling

Tokens are defined in `src/app/globals.css` under `@theme`. Use the Tailwind `brand`
namespace (`bg-brand-surface`, `text-brand-muted`, …) and `var(--color-collection-*)`
for collection accents.

**No hardcoded hex in components.** Two themes are selected by `data-theme` on `<html>`
— any new color must be added to **both** theme blocks. (Root §9)

## Before you commit

```bash
npm run lint    # baseline is ZERO errors; leave no new warnings in files you touch
npm test        # vitest run
npm run build
```

Test the search runtime through its `read`/`subscribe`/`send` interface with scripted
in-memory adapters. Do not assert on private reducer state.

## Not product surface

`src/app/chat/` only redirects old links to `/search`, and `src/app/onboarding-preview/`
is a development-only preview that 404s in production. (Root §10)
