"use client";

import { useLayoutEffect, useRef } from "react";

import type {
  SearchExperience,
  SearchExperienceSnapshot,
} from "./types";

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

}
