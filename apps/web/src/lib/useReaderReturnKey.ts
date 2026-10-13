"use client";

import { useCallback, useState } from "react";
import { markReaderReturn, newReaderReturnKey, type ReaderOrigin } from "./readerNavigation";

/**
 * The return key for a reader link, stable between navigations so the href is
 * the URL its prefetch warmed. `markReturn` is the link's onNavigate: it writes
 * the marker for this same-tab navigation, then moves the link to a fresh key.
 * A key is therefore marked at most once, and a later new-tab open of the same
 * link (whose tab may inherit this tab's sessionStorage) never finds a marker
 * that would make its Back call router.back() with no history behind it.
 */
export function useReaderReturnKey(origin: ReaderOrigin) {
  const [returnKey, setReturnKey] = useState(newReaderReturnKey);
  const markReturn = useCallback(() => {
    markReaderReturn(returnKey, origin);
    // After the click, not during it: a synchronous update would re-render every
    // Library row ahead of the navigation's own render. Usually the page has
    // unmounted by then and this is a no-op.
    window.setTimeout(() => setReturnKey(newReaderReturnKey()), 0);
  }, [origin, returnKey]);
  return { returnKey, markReturn };
}
