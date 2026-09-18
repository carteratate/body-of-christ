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
| Draft quota/collection rules | `src/lib/search-draft.ts` | Re-derive focused eligibility from a raw quota int. |

(Root §12, §14, §18)

## Shells and routes

`src/components/layout/AuthenticatedRouteShell.tsx` picks between `AppShell`
(authenticated) and `GuestShell` by matching the pathname against its own
`AUTHENTICATED_ROUTES` list. **A new authenticated route must be added to that list or
it silently renders in the guest shell.**

Authenticated pages live at the bare path; the guest mirror is a sibling under
`/guest/` or `/search/guest`. They share components via an `isGuest` prop rather than
forking — update both together. (Root §10, §11, §13)

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

## Known dead code

`src/components/chat/ChatShell.tsx` and `streamMessage` in `api.ts` are unreachable —
`/chat` redirects to `/search`. `src/app/icon-preview/`, `src/app/onboarding-preview/`,
and `src/app/prototypes/` are design drafts, not product surface. (Root §3, §17)
