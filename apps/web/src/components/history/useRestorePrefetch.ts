"use client";

import { useCallback, useEffect, useRef } from "react";
import { useAppContext } from "@/components/layout/AppShell";
import type { SearchSummaryV2 } from "@/lib/api";
import { prefetchSavedSearchResults } from "@/lib/saved-search-cache";

// Long enough that sweeping the pointer or tabbing across rows warms nothing.
const INTENT_DELAY_MS = 150;
// A search joins history when its results are ready, but explanations are still
// being saved for a while after. Prefetching one that young could cache results
// with explanations missing. created_at is server time; a client clock running
// fast by more than this would let such a search through.
const RECENT_SEARCH_MS = 60_000;

function canHover(): boolean {
  return typeof window.matchMedia === "function"
    && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}

/**
 * Warms a saved search's results when a pointer rests on its row or keyboard
 * focus lands on it. Touch devices never prefetch. Only one prefetch is in
 * flight at a time; leaving a row cancels a pending one but lets a started
 * request finish, so a click that follows can still use it.
 */
export function useRestorePrefetch() {
  const { token, activeSearchId, pendingSearch } = useAppContext();
  const timerRef = useRef<number | null>(null);
  const inFlightRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  const schedule = useCallback((search: SearchSummaryV2) => {
    cancel();
    if (!token || !canHover()) return;
    if (search.id === activeSearchId || search.id === pendingSearch?.id) return;
    const createdAt = Date.parse(search.created_at);
    if (!Number.isFinite(createdAt) || Date.now() - createdAt < RECENT_SEARCH_MS) return;
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      inFlightRef.current?.abort();
      const controller = new AbortController();
      inFlightRef.current = controller;
      prefetchSavedSearchResults(token, search.id, controller.signal);
    }, INTENT_DELAY_MS);
  }, [activeSearchId, cancel, pendingSearch?.id, token]);

  // Leaving the page drops the prefetch's claim on its request. The cache waits a
  // task before cancelling, so a restore started by the same navigation can take
  // the request over; otherwise a stalled prefetch would hold the request open
  // and every restore retry would join it instead of trying again.
  useEffect(() => () => {
    cancel();
    inFlightRef.current?.abort();
    inFlightRef.current = null;
  }, [cancel]);

  return { schedule, cancel };
}
