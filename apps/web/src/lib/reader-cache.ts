// Reader data cache: tables of contents and chapters, shared by DocumentOverview
// and DocumentReader for the life of the page.
//
// Both are corpus data, identical for every signed-in reader, so authenticated
// entries share one audience rather than being keyed by access token (a token
// refresh would otherwise miss every entry). Guest entries are keyed by guest
// session token, because a guest may only read documents that session retrieved.
//
// A cached entry can outlive a corpus republish. DocumentReader evicts a
// document when a chapter is not found or when a chapter's chunk_count
// disagrees with its table of contents; see invalidateReaderDocument. A
// republish that changes neither (corrected text, same keys and count) is
// caught only by the TTL, which also bounds how long a guest's cached reads
// outlast the server revoking that guest session.

import { getReaderChapter, getToc, type ReaderChapter, type TocResponse } from "@/lib/api";
import { createRequestCache } from "@/lib/client-cache";

// The Summa's table of contents is 1.1 MB of JSON and several times that as
// objects, so only a few documents are kept.
const TOC_CACHE_SIZE = 4;
const CHAPTER_CACHE_SIZE = 30;
const READER_CACHE_TTL_MS = 30 * 60 * 1000;

const tocCache = createRequestCache<TocResponse>({ maxEntries: TOC_CACHE_SIZE, ttlMs: READER_CACHE_TTL_MS });
const chapterCache = createRequestCache<ReaderChapter>({ maxEntries: CHAPTER_CACHE_SIZE, ttlMs: READER_CACHE_TTL_MS });

export interface ReaderAccess {
  token: string | null;
  guestToken?: string;
}

function audience(access: ReaderAccess): string {
  return access.guestToken ? `guest:${access.guestToken}` : "auth";
}

function documentPrefix(access: ReaderAccess, docId: string): string {
  return `${JSON.stringify([audience(access), docId])}\n`;
}

function chapterCacheKey(access: ReaderAccess, docId: string, chapterKey: string): string {
  return `${documentPrefix(access, docId)}${chapterKey}`;
}

// Only the anchor request carries a highlight; a chapter served from the cache
// must not re-highlight whatever passage first brought it in.
function withoutHighlight(chapter: ReaderChapter): ReaderChapter {
  return chapter.highlight_anchor === null ? chapter : { ...chapter, highlight_anchor: null };
}

export function loadToc(access: ReaderAccess, docId: string, signal?: AbortSignal): Promise<TocResponse> {
  return tocCache.get(
    documentPrefix(access, docId),
    (shared) => getToc(access.token ?? "", docId, shared, access.guestToken),
    signal,
  );
}

export function loadChapter(
  access: ReaderAccess,
  docId: string,
  chapterKey: string,
  signal?: AbortSignal,
): Promise<ReaderChapter> {
  return chapterCache.get(
    chapterCacheKey(access, docId, chapterKey),
    async (shared) => withoutHighlight(
      await getReaderChapter(access.token ?? "", docId, { chapter: chapterKey, signal: shared, guestToken: access.guestToken }),
    ),
    signal,
  );
}

/**
 * Opens a document by anchor, or at its first chapter when no anchor is given.
 * The server picks the chapter, so this always goes to the network; the result
 * is then stored under the chapter key it returned.
 */
export async function loadEntryChapter(
  access: ReaderAccess,
  docId: string,
  options: { anchor?: string; signal?: AbortSignal },
): Promise<ReaderChapter> {
  const chapter = await getReaderChapter(access.token ?? "", docId, {
    anchor: options.anchor,
    signal: options.signal,
    guestToken: access.guestToken,
  });
  chapterCache.set(chapterCacheKey(access, docId, chapter.chapter_key), withoutHighlight(chapter));
  return chapter;
}

export function isChapterCached(access: ReaderAccess, docId: string, chapterKey: string): boolean {
  return chapterCache.has(chapterCacheKey(access, docId, chapterKey));
}

/** Warms the cache. Aborting the signal never affects a caller who joined it. */
export function prefetchChapter(access: ReaderAccess, docId: string, chapterKey: string, signal: AbortSignal): void {
  loadChapter(access, docId, chapterKey, signal).catch(() => undefined);
}

export function invalidateReaderDocument(access: ReaderAccess, docId: string): void {
  const prefix = documentPrefix(access, docId);
  tocCache.evict(prefix);
  chapterCache.evictWhere((key) => key.startsWith(prefix));
}

export function isNotFoundError(error: unknown): boolean {
  return error instanceof Error && error.message === "API error 404";
}
