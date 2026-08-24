"use client";

import { useSyncExternalStore } from "react";
import type { SearchExperience, SearchExperienceSnapshot } from "./types";

/** React subscription wiring only; lifecycle transitions stay inside the runtime. */
export function useSearchExperience(runtime: SearchExperience): SearchExperienceSnapshot {
  return useSyncExternalStore(runtime.subscribe, runtime.read, runtime.read);
}
