export interface CollectionMeta {
  key: string;
  label: string;
  color: string;
  hex: string;
}

// The collections after corpus cleanup 5.1b (Carter, 22 Nov 2026): the three papal
// collections are one, Canon Law is Church law, and Medieval is Theology & Spirituality.
// Each keeps an old collection's colour. The API's list is `CANONICAL_COLLECTIONS` in
// `services/api/app/rag/constants.py`.
export const COLLECTIONS: CollectionMeta[] = [
  { key: "bible",          label: "Bible",                   color: "var(--color-collection-bible)",          hex: "#d4885a" },
  { key: "catechism",      label: "Catechism",               color: "var(--color-collection-catechism)",      hex: "#5b9bd4" },
  { key: "summa",          label: "Summa Theologica",        color: "var(--color-collection-summa)",          hex: "#55cc88" },
  { key: "papal",          label: "Papal documents",         color: "var(--color-collection-papal)",          hex: "#e8c040" },
  { key: "councils",       label: "Councils",                color: "var(--color-collection-councils)",       hex: "#60d4c8" },
  { key: "church-fathers", label: "Church Fathers",          color: "var(--color-collection-church-fathers)", hex: "#b070d4" },
  { key: "theologians",    label: "Theology & Spirituality", color: "var(--color-collection-theologians)",    hex: "#90a0a8" },
  { key: "church-law",     label: "Church law",              color: "var(--color-collection-church-law)",     hex: "#e84040" },
];

export const ALL_COLLECTION_KEYS: string[] = COLLECTIONS.map((c) => c.key);

/**
 * An old collection key and what it means now: its new collection, read whole or only
 * for some genres. 5.1b.3 rewrote every stored key and the API no longer accepts the old
 * ones (5.1b.4), but a browser can still hold one: a guest's saved draft or settings, or
 * a page loaded before the change. The web translates it here and never sends it.
 * `genres` are the only genres the old key read; `withoutGenres` the genres it did not
 * (it read the rest, and documents with none).
 */
export interface LegacyCollection {
  readonly key: string;
  readonly genres?: readonly string[];
  readonly withoutGenres?: readonly string[];
}

export const LEGACY_COLLECTIONS: Readonly<Record<string, LegacyCollection>> = {
  encyclicals: { key: "papal", genres: ["encyclical"] },
  "apostolic-exhortations": { key: "papal", genres: ["apostolic-exhortation"] },
  "papal-documents": { key: "papal", withoutGenres: ["encyclical", "apostolic-exhortation"] },
  "canon-law": { key: "church-law" },
  medieval: { key: "theologians" },
};

/** The collection key in today's vocabulary: an old key's new one, any other unchanged. */
export function canonicalCollectionKey(key: string): string {
  return Object.hasOwn(LEGACY_COLLECTIONS, key) ? LEGACY_COLLECTIONS[key].key : key;
}

/** A collection's entry, for an old key too, so a stored old key shows its new name. */
export function getCollectionMeta(key: string): CollectionMeta | undefined {
  const canonical = canonicalCollectionKey(key);
  return COLLECTIONS.find((c) => c.key === canonical);
}

/** Keys in today's vocabulary, in order, each once; unknown keys are kept for the caller to drop. */
export function canonicalCollectionKeys(keys: readonly string[]): string[] {
  return [...new Set(keys.map(canonicalCollectionKey))];
}

/**
 * Documents in today's collection vocabulary: until 5.1b.3 rewrites them, documents
 * carry old keys, so the three papal collections arrive as three runs. Sorted as the
 * API orders them (collection, then year with undated last, then title), so a merged
 * collection lists its documents by date.
 */
export function canonicalDocuments<T extends {
  readonly collection: string; readonly year: number | null; readonly title: string;
}>(documents: readonly T[]): T[] {
  return documents
    .map((doc) => {
      const collection = canonicalCollectionKey(doc.collection);
      return collection === doc.collection ? doc : { ...doc, collection };
    })
    .sort((a, b) => a.collection.localeCompare(b.collection)
      || (a.year ?? Number.MAX_SAFE_INTEGER) - (b.year ?? Number.MAX_SAFE_INTEGER)
      || a.title.localeCompare(b.title));
}

export function hexToRgb(hex: string): string {
  if (!hex.startsWith("#") || hex.length < 7) return "196,151,42";
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}
