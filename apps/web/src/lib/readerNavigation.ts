export type ReaderOrigin = "search" | "saved" | "library" | "history";

const STORAGE_PREFIX = "theocorpus-reader-return:";
const MAX_AGE_MS = 2 * 60 * 60 * 1000;
const KEY_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface ReturnMarker {
  origin: ReaderOrigin;
  createdAt: number;
}

export function createReaderReturnKey(origin: ReaderOrigin): string | null {
  try {
    const key = crypto.randomUUID();
    const marker: ReturnMarker = { origin, createdAt: Date.now() };
    sessionStorage.setItem(`${STORAGE_PREFIX}${key}`, JSON.stringify(marker));
    return key;
  } catch {
    return null;
  }
}

export function isReaderReturnKey(value: string | null): value is string {
  return value !== null && KEY_RE.test(value);
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
    if (!raw) return false;
    const marker = JSON.parse(raw) as Partial<ReturnMarker>;
    return marker.origin === origin
      && typeof marker.createdAt === "number"
      && marker.createdAt <= Date.now() + 60_000
      && Date.now() - marker.createdAt <= MAX_AGE_MS;
  } catch {
    return false;
  }
}
