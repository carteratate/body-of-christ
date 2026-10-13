"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { usePendingNavigation } from "@/components/common/NavPending";
import { consumeReaderReturnKey, hasReaderReturnMarker, type ReaderOrigin } from "@/lib/readerNavigation";

const FALLBACK: Record<ReaderOrigin, string> = {
  saved: "/bookmarks",
  history: "/history",
  search: "/search",
  library: "/sources",
};

/**
 * The reader's Back, shared by the overview and the chapter view. A tab that
 * entered through an in-app link pops its history (instant, from the router
 * cache). Otherwise Back opens a fixed page — a server round trip — so that page
 * is prefetched as soon as the reader mounts, and `pending` drives the cue
 * while it loads.
 */
export function useReaderBack({ isGuest, origin, returnKey, preview }: {
  isGuest: boolean;
  origin: ReaderOrigin;
  returnKey: string | null;
  preview: boolean;
}) {
  const router = useRouter();
  const { pending, push } = usePendingNavigation();
  const fallback = isGuest ? (preview ? "/search/guest?preview=1" : "/search/guest") : FALLBACK[origin];

  useEffect(() => {
    if (isGuest || !hasReaderReturnMarker(returnKey, origin)) router.prefetch(fallback);
  }, [fallback, isGuest, origin, returnKey, router]);

  const goBack = useCallback(() => {
    if (isGuest) {
      consumeReaderReturnKey(returnKey, origin);
      push(fallback);
      return;
    }
    if (consumeReaderReturnKey(returnKey, origin)) router.back();
    else push(fallback);
  }, [fallback, isGuest, origin, push, returnKey, router]);

  return { goBack, pending };
}
