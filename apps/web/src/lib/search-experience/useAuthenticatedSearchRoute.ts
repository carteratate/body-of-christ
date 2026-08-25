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
  const consumedRestoreRoute = useRef<string | null>(null);
  const consumedExploreRoute = useRef<string | null>(null);
  const previousCredential = useRef(credential);
  const exploreOwner = useRef(userId);

  useLayoutEffect(() => {
    routeRestoreId.current = restoreId;
  }, [restoreId]);

  useLayoutEffect(() => {
    if (exploreOwner.current === userId && credential) return;
    exploreOwner.current = userId;
    consumedRestoreRoute.current = null;
    consumedExploreRoute.current = null;
  }, [credential, userId]);

  useLayoutEffect(() => {
    if (credential === previousCredential.current) return;
    previousCredential.current = credential;
    experience.send({ type: "credentials-changed" });
  }, [credential, experience]);

  useLayoutEffect(() => {
    if (!userId || !credential) return;
    if (restoreId) {
      const routeKey = `${userId}\u0000${restoreId}`;
      if (consumedRestoreRoute.current !== routeKey) {
        consumedRestoreRoute.current = routeKey;
        experience.send({ type: "restore", searchId: restoreId });
      }
      return;
    }
    consumedRestoreRoute.current = null;
    if (snapshot.status === "restoring"
      || snapshot.status === "restored-passages"
      || (snapshot.status === "failure" && snapshot.failure.kind === "restore")) {
      experience.send({ type: "leave-restore" });
    }
  }, [credential, experience, restoreId, snapshot, userId]);

  useEffect(() => {
    if (!exploreQuery) {
      consumedExploreRoute.current = null;
      return;
    }
    if (!credential) return;
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

  const queryMoreLike = useCallback((content: string, label: string) => {
    experience.send({
      type: "queue-explore",
      query: content,
      label,
      defaults,
    });
    if (routeRestoreId.current) {
      replaceWithSearchRoute();
    }
  }, [defaults, experience, replaceWithSearchRoute]);

  return { queryMoreLike };
}
