"use client";

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

// Long enough that sweeping the pointer or tabbing across a list warms nothing.
export const INTENT_PREFETCH_DELAY_MS = 150;

interface Options {
  /** False suppresses every prefetch, e.g. for a row whose click is swallowed. */
  enabled?: boolean;
}

/**
 * Prefetches `href` when the reader shows intent instead of when the link comes
 * into view: after the mouse rests on it or keyboard focus stays on it for
 * INTENT_PREFETCH_DELAY_MS. Every route here is dynamic, so a prefetch fetches
 * down to the destination's loading.tsx, which is what lets the click show that
 * loading screen immediately.
 *
 * A prefetch only helps once it has finished, and it takes two round trips
 * (route tree, then segments). A click that lands while one is still in flight
 * waits for it. Measured on Next 16.2.2, local production build, every request
 * delayed 400ms, Library → reader:
 *   no prefetch                              445ms
 *   prefetch finished before the click        25ms
 *   prefetch started 300ms before the click  540ms
 *   prefetch started 100ms before (a press)  743ms
 * So never on press: the press-to-click gap is too short, and it makes the click
 * slower. Touch, which has no hover, relies on the pending cue instead.
 */
export function useIntentPrefetch(href: string, { enabled = true }: Options = {}) {
  const router = useRouter();
  const timer = useRef<number | null>(null);

  const cancel = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const schedule = useCallback(() => {
    cancel();
    if (!enabled) return;
    timer.current = window.setTimeout(() => {
      timer.current = null;
      router.prefetch(href);
    }, INTENT_PREFETCH_DELAY_MS);
  }, [cancel, enabled, href, router]);

  useEffect(() => cancel, [cancel]);

  return {
    onPointerEnter(event: React.PointerEvent) {
      if (event.pointerType === "mouse") schedule();
    },
    onPointerLeave: cancel,
    // Keyboard focus only: focus moved by script (after a delete, on open) is not intent.
    onFocus(event: React.FocusEvent<HTMLElement>) {
      if (event.currentTarget.matches(":focus-visible")) schedule();
    },
    onBlur: cancel,
  };
}
