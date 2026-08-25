"use client";

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

import type {
  SearchExperience,
  SearchExperienceSnapshot,
  SearchRequest,
} from "./types";

interface SearchDefaults {
  readonly collections: readonly string[];
  readonly translation: string;
  readonly quota: number;
}

interface AuthenticatedSearchRouteOptions {
  readonly experience: SearchExperience;
  readonly snapshot: SearchExperienceSnapshot;
  readonly restoreId: string | null;
  readonly userId: string | null;
  readonly credential: string | null;
  readonly exploreQuery: string | null;
  readonly exploreReference: string | null;
  readonly defaults: SearchDefaults;
  readonly replaceWithSearchRoute: () => void;
}

function exploreLabel(query: string, reference: string | null): string {
  const supplied = reference?.trim();
  if (supplied) return supplied;
  const clipped = query.slice(0, 60).replace(/\s+\S*$/, "");
  return clipped + (query.length > 60 ? "…" : "");
}

function createExploreRequest(
  query: string,
  label: string,
  defaults: SearchDefaults,
): SearchRequest {
  return {
    query,
    collections: defaults.collections,
    translation: defaults.translation,
    quota: defaults.quota,
    origin: "explore",
    exploreLabel: label,
  };
}

export function useAuthenticatedSearchRoute({
  experience,
  snapshot,
  restoreId,
  userId,
  credential,
  exploreQuery,
  exploreReference,
  defaults,
  replaceWithSearchRoute,
}: AuthenticatedSearchRouteOptions) {
  const routeRestoreId = useRef(restoreId);
  const queuedExplore = useRef<SearchRequest | null>(null);
  const consumedExploreRoute = useRef<string | null>(null);
  const exploreTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previousCredential = useRef(credential);
  const exploreOwner = useRef(userId);

  useLayoutEffect(() => {
    routeRestoreId.current = restoreId;
  }, [restoreId]);

  useLayoutEffect(() => {
    if (exploreOwner.current === userId && credential) return;
    exploreOwner.current = userId;
    queuedExplore.current = null;
    consumedExploreRoute.current = null;
    if (exploreTimer.current) {
      clearTimeout(exploreTimer.current);
      exploreTimer.current = null;
    }
  }, [credential, userId]);

  useLayoutEffect(() => {
    if (credential === previousCredential.current) return;
    previousCredential.current = credential;
    experience.send({ type: "credentials-changed" });
  }, [credential, experience]);

  useLayoutEffect(() => {
    if (!userId || !credential) return;
    if (restoreId) {
      experience.send({ type: "restore", searchId: restoreId });
      return;
    }
    if (snapshot.status === "restoring"
      || snapshot.status === "restored-results"
      || (snapshot.status === "failure" && snapshot.failure.kind === "restore")) {
      experience.send({ type: "cancel" });
    }
  }, [credential, experience, restoreId, snapshot, userId]);

  useEffect(() => {
    if (restoreId || !credential) return;
    const request = queuedExplore.current;
    if (!request) return;
    queuedExplore.current = null;
    experience.send({ type: "submit", request });
  }, [credential, experience, restoreId]);

  useEffect(() => {
    if (!exploreQuery || !credential) return;
    const routeKey = `${exploreQuery}\u0000${exploreReference ?? ""}`;
    if (consumedExploreRoute.current === routeKey) return;
    consumedExploreRoute.current = routeKey;
    experience.send({
      type: "submit",
      request: createExploreRequest(
        exploreQuery,
        exploreLabel(exploreQuery, exploreReference),
        defaults,
      ),
    });
    replaceWithSearchRoute();
  }, [credential, defaults, experience, exploreQuery, exploreReference, replaceWithSearchRoute]);

  useEffect(() => () => {
    if (exploreTimer.current) clearTimeout(exploreTimer.current);
  }, []);

  const queryMoreLike = useCallback((content: string, label: string) => {
    const current = experience.read();
    const submitted = current.status === "active-search"
      || current.status === "restored-results"
      || (current.status === "failure" && current.request)
      ? current.request
      : null;
    const request = createExploreRequest(content, label, submitted ?? defaults);
    if (routeRestoreId.current) {
      queuedExplore.current = request;
      replaceWithSearchRoute();
      return;
    }
    if (exploreTimer.current) clearTimeout(exploreTimer.current);
    exploreTimer.current = setTimeout(() => {
      exploreTimer.current = null;
      experience.send({ type: "submit", request });
    }, 300);
  }, [defaults, experience, replaceWithSearchRoute]);

  const cancelPendingExplore = useCallback(() => {
    queuedExplore.current = null;
    if (!exploreTimer.current) return;
    clearTimeout(exploreTimer.current);
    exploreTimer.current = null;
  }, []);

  return { queryMoreLike, cancelPendingExplore };
}
