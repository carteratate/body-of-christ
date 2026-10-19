"use client";

import { useEffect, useSyncExternalStore } from "react";
import type { SearchExperience, SearchExperienceSnapshot } from "./types";

interface RuntimeLease {
  subscribers: number;
}

const runtimeLeases = new WeakMap<SearchExperience, RuntimeLease>();

/** React subscription wiring only; lifecycle transitions stay inside the runtime. */
export function useSearchExperience(
  runtime: SearchExperience,
  { disposeOnRelease = true }: { readonly disposeOnRelease?: boolean } = {},
): SearchExperienceSnapshot {
  useEffect(() => {
    // A runtime owned above the page (AppShell's, see useSearchPageExperience)
    // outlives its subscribers; its owner disposes it.
    if (!disposeOnRelease) return;
    const lease = runtimeLeases.get(runtime) ?? { subscribers: 0 };
    runtimeLeases.set(runtime, lease);
    lease.subscribers += 1;
    return () => {
      lease.subscribers -= 1;
      queueMicrotask(() => {
        if (lease.subscribers > 0) return;
        runtimeLeases.delete(runtime);
        runtime.send({ type: "dispose" });
      });
    };
  }, [disposeOnRelease, runtime]);
  return useSyncExternalStore(runtime.subscribe, runtime.read, runtime.read);
}
