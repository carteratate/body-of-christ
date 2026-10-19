"use client";

import { useLayoutEffect, useRef } from "react";

import type {
  SearchExperience,
  SearchExperienceSnapshot,
} from "./types";
import { routeSearchId } from "./view";

const SEARCH_PATH = "/search";

/**
 * Point the current history entry at `searchId` without a navigation, so Back
 * from the reader (or a reload) returns to the search the page holds.
 *
 * The write keeps Next's own history state, whose `__NA` marker makes Next's
 * patched `replaceState` skip its router sync. A synced write dispatches a
 * router restore, which discards any navigation still in flight: a search that
 * finished while a sidebar link was loading would cancel that click. Back and
 * forward still work, since Next restores from `location` and this state. The
 * cost is that `useSearchParams` does not see the write, so compare against
 * `location`, not the hook's `restoreId`.
 *
 * Only `/search` itself is rewritten: a search completing while the reader is
 * open must not touch the reader's URL; the page syncs again when it mounts.
 */
function replaceRestoreParam(searchId: string | null) {
  if (window.location.pathname !== SEARCH_PATH) return;
  const url = new URL(window.location.href);
  if ((url.searchParams.get("restore") || null) === searchId) return;
  if (searchId) url.searchParams.set("restore", searchId);
  else url.searchParams.delete("restore");
  window.history.replaceState(
    { ...window.history.state },
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}

interface AuthenticatedSearchRouteOptions {
  readonly experience: SearchExperience;
  readonly snapshot: SearchExperienceSnapshot;
  readonly restoreId: string | null;
  readonly userId: string | null;
  readonly credential: string | null;
}

export function useAuthenticatedSearchRoute({
  experience,
  snapshot,
  restoreId,
  userId,
  credential,
}: AuthenticatedSearchRouteOptions) {
  const consumedRestoreRoute = useRef<string | null>(null);
  const previousRestoreRoute = useRef(restoreId);
  const previousCredential = useRef(credential);

  useLayoutEffect(() => {
    if (credential) return;
    consumedRestoreRoute.current = null;
  }, [credential]);

  useLayoutEffect(() => {
    if (credential === previousCredential.current) return;
    previousCredential.current = credential;
    experience.send({ type: "credentials-changed" });
  }, [credential, experience]);

  useLayoutEffect(() => {
    if (!userId || !credential) return;
    const previousRestoreId = previousRestoreRoute.current;
    previousRestoreRoute.current = restoreId;
    if (restoreId) {
      const routeKey = `${userId}\u0000${restoreId}`;
      if (consumedRestoreRoute.current !== routeKey) {
        consumedRestoreRoute.current = routeKey;
        // A no-op when the runtime already holds this search (see runtime.ts).
        experience.send({ type: "restore", searchId: restoreId });
      }
    } else {
      consumedRestoreRoute.current = null;
      // Only a route that moved off a restored search (browser Back to a bare
      // /search entry) leaves it. Arriving at bare /search keeps whatever the
      // held runtime shows, restored or live, and the write below names it.
      if (previousRestoreId
        && (snapshot.status === "restoring"
          || snapshot.status === "restored-passages"
          || (snapshot.status === "failure" && snapshot.failure.kind === "restore"))) {
        experience.send({ type: "leave-restore" });
      }
    }
    // The URL names what the page holds: the saved search once a live one
    // completes, nothing while a new one runs (so a stale `?restore=` cannot
    // bring an older search back). Read after the sends above. An idle runtime
    // leaves the URL alone: New Search resets before its own push lands, and
    // clearing here would strip the search from the entry Back returns to.
    const held = experience.read();
    if (held.status !== "idle") replaceRestoreParam(routeSearchId(held));
  }, [credential, experience, restoreId, snapshot, userId]);

}
