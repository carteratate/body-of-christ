export type ReaderOrigin = "search" | "saved" | "library" | "history";

const STORAGE_PREFIX = "theocorpus-reader-return:";
const MAX_AGE_MS = 2 * 60 * 60 * 1000;
const KEY_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface ReturnMarker {
  origin: ReaderOrigin;
  createdAt: number;
}

/**
 * A fresh return key, or null if the browser can't make one (the reader then
 * takes its deterministic fallback). Create it once per link, not per click, so
 * the link's href is stable and is exactly the URL its prefetch warmed.
 */
export function newReaderReturnKey(): string | null {
  try {
    return crypto.randomUUID();
  } catch {
    return null;
  }
}

/**
 * Record that this tab is about to enter the reader through `key`. Call it only
 * for a same-tab navigation (a Link's onNavigate): a new tab must not inherit
 * a marker, or its Back would call router.back() with no history behind it.
 */
export function markReaderReturn(key: string | null, origin: ReaderOrigin): void {
  if (!isReaderReturnKey(key)) return;
  try {
    const marker: ReturnMarker = { origin, createdAt: Date.now() };
    sessionStorage.setItem(`${STORAGE_PREFIX}${key}`, JSON.stringify(marker));
  } catch {
    // Storage unavailable: the reader falls back to its in-app destination.
  }
}

/** The reader URL for an entry point; params in a fixed order so hrefs are stable. */
export function readerHref({
  docId,
  origin,
  returnKey,
  anchor,
  chapter,
  guest = false,
  guideBack = false,
  preview = false,
}: {
  docId: string;
  origin: ReaderOrigin;
  returnKey: string | null;
  anchor?: string | null;
  chapter?: string | null;
  guest?: boolean;
  guideBack?: boolean;
  preview?: boolean;
}): string {
  const params = new URLSearchParams({ from: origin });
  if (returnKey) params.set("returnKey", returnKey);
  if (anchor) params.set("anchor", anchor);
  else if (chapter) params.set("chapter", chapter);
  if (guest && guideBack) params.set("guideBack", "1");
  if (guest && preview) params.set("preview", "1");
  return `${guest ? "/reader/guest" : "/reader"}/${docId}?${params.toString()}`;
}

export function isReaderReturnKey(value: string | null): value is string {
  return value !== null && KEY_RE.test(value);
}

function validMarker(raw: string | null, origin: ReaderOrigin): boolean {
  if (!raw) return false;
  try {
    const marker = JSON.parse(raw) as Partial<ReturnMarker>;
    return marker.origin === origin
      && typeof marker.createdAt === "number"
      && marker.createdAt <= Date.now() + 60_000
      && Date.now() - marker.createdAt <= MAX_AGE_MS;
  } catch {
    return false;
  }
}

/** Whether Back would return through history, without using the marker up. */
export function hasReaderReturnMarker(key: string | null, origin: ReaderOrigin): boolean {
  if (!isReaderReturnKey(key)) return false;
  try {
    return validMarker(sessionStorage.getItem(`${STORAGE_PREFIX}${key}`), origin);
  } catch {
    return false;
  }
}

/**
 * Consume a same-tab marker created immediately before entering Reader.
 * A copied or deep-linked Reader URL has no matching marker, so callers use a
 * deterministic in-app fallback instead of trusting arbitrary browser history.
 */
export function consumeReaderReturnKey(key: string | null, origin: ReaderOrigin): boolean {
  if (!isReaderReturnKey(key)) return false;
  const storageKey = `${STORAGE_PREFIX}${key}`;
  try {
    const raw = sessionStorage.getItem(storageKey);
    sessionStorage.removeItem(storageKey);
    return validMarker(raw, origin);
  } catch {
    return false;
  }
}
