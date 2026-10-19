/**
 * Excerpt-only documents (issue #265). A document whose rights are not cleared keeps
 * its passages in search, but TheoCorpus does not offer its full text: the API refuses
 * its reader with 403 `reader_restricted`, and every link that would open the reader
 * points at the official source instead.
 *
 * `reader_access` is absent on responses from an API older than migration 0041, and
 * on results saved in the browser before it; absent means full.
 */
export type ReaderAccess = "full" | "excerpt";

export const READER_RESTRICTED_CODE = "reader_restricted";

export interface ReaderAccessFields {
  reader_access?: ReaderAccess | null;
  source_url?: string | null;
}

export function isExcerptOnly(fields: ReaderAccessFields | null | undefined): boolean {
  return fields?.reader_access === "excerpt";
}

/** The source link for an excerpt-only document, or null when there is none to give. */
export function excerptSourceUrl(fields: ReaderAccessFields | null | undefined): string | null {
  if (!isExcerptOnly(fields)) return null;
  const url = fields?.source_url;
  return typeof url === "string" && /^https?:\/\//.test(url) ? url : null;
}

export function readerAccessValue(value: unknown): ReaderAccess | null {
  return value === "excerpt" || value === "full" ? value : null;
}
