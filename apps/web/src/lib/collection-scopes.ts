import { genreLabel } from "./attribution";
import data from "./collection-scopes.json";
import { canonicalCollectionKey, LEGACY_COLLECTIONS } from "./collections";

/**
 * Which collections a search can narrow by genre and issuer (corpus cleanup 5.1a), and
 * the values each one holds, in the order the filter lists them. Generated from
 * `datapipeline/registry/works.json` by `collection-scopes.test.ts` (`npx vitest run -u
 * collection-scopes` rewrites it); the API's vocabulary is `GENRES_BY_COLLECTION` and
 * `ISSUERS_BY_COLLECTION` in `services/api/app/rag/constants.py`.
 */
export type ScopeFacet = "genres" | "issuers";

export interface ScopeValue {
  readonly value: string;
  readonly label: string;
}

export interface CollectionScopeOptions {
  readonly genres: readonly ScopeValue[];
  readonly issuers: readonly ScopeValue[];
  /** Published documents per genre and issuer: `documents[genre][issuer]`. */
  readonly documents: Readonly<Record<string, Readonly<Record<string, number>>>>;
}

/** One collection's selection as the API takes it: the values searched, absent = all. */
export interface ScopeSelection {
  genres?: string[];
  issuers?: string[];
}

export interface RegistryWork {
  readonly collection: string;
  readonly genre?: string | null;
  readonly issuer?: string | null;
  readonly issuer_label?: string | null;
  readonly year?: number | null;
}

// The collections the API can narrow. Roman Curia joins with 5.3a.
export const SCOPED_COLLECTIONS = ["papal"] as const;

export const COLLECTION_SCOPES: Readonly<Record<string, CollectionScopeOptions>> = data;

export function scopeOptions(collection: string): CollectionScopeOptions | undefined {
  return COLLECTION_SCOPES[collection];
}

/** A genre's label as the cards print it ("Apostolic letter"), and "Other". */
export function scopeGenreLabel(genre: string): string {
  return genreLabel(genre) ?? "Other";
}

/** A pope's name without "Pope": the filter's heading says Pope. */
export function scopeIssuerLabel(label: string): string {
  return label.replace(/^Pope\s+/, "");
}

/** What a published work set says each scoped collection holds. */
export function buildCollectionScopes(
  works: readonly RegistryWork[],
): Record<string, CollectionScopeOptions> {
  const out: Record<string, CollectionScopeOptions> = {};
  for (const collection of SCOPED_COLLECTIONS) {
    const genres = new Map<string, number>();
    const issuers = new Map<string, { label: string; first: number }>();
    const documents: Record<string, Record<string, number>> = {};
    for (const work of works) {
      // A work without a genre is not published (held for permission). The registry
      // keeps old collection keys until 5.1b.3, so a work counts under its new one.
      if (canonicalCollectionKey(work.collection) !== collection || !work.genre) continue;
      genres.set(work.genre, (genres.get(work.genre) ?? 0) + 1);
      if (work.issuer && work.issuer_label) {
        const seen = issuers.get(work.issuer);
        const year = work.year ?? Number.MAX_SAFE_INTEGER;
        issuers.set(work.issuer, {
          label: work.issuer_label,
          first: Math.min(seen?.first ?? Number.MAX_SAFE_INTEGER, year),
        });
        const row = (documents[work.genre] ??= {});
        row[work.issuer] = (row[work.issuer] ?? 0) + 1;
      }
    }
    out[collection] = {
      // The kind with most documents first; "other" always last.
      genres: [...genres]
        .sort(([a, an], [b, bn]) =>
          Number(a === "other") - Number(b === "other") || bn - an || a.localeCompare(b))
        .map(([value]) => ({ value, label: scopeGenreLabel(value) })),
      // Popes in the order of their first document here: the order of their pontificates.
      issuers: [...issuers]
        .sort(([, a], [, b]) => a.first - b.first)
        .map(([value, { label }]) => ({ value, label: scopeIssuerLabel(label) })),
      // Keys sorted so the generated file only changes when the counts do.
      documents: Object.fromEntries(Object.keys(documents).sort().map((genre) => [
        genre,
        Object.fromEntries(Object.entries(documents[genre]).sort(([a], [b]) => a.localeCompare(b))),
      ])),
    };
  }
  return out;
}

export interface ScopeValueCount extends ScopeValue {
  readonly documents: number;
}

/**
 * The values each list shows for the current selection, with their counts: a kind
 * counts the documents of the popes still ticked, and a pope the documents of the
 * kinds still ticked. A value with none is left out, so choosing a pope narrows the
 * Kind list to that pope's kinds, and choosing a kind narrows the Pope list.
 */
export function visibleScopeValues(
  options: CollectionScopeOptions,
  excluded: { readonly genres: readonly string[]; readonly issuers: readonly string[] } | undefined,
): Record<ScopeFacet, ScopeValueCount[]> {
  const offGenres = new Set(excluded?.genres ?? []);
  const offIssuers = new Set(excluded?.issuers ?? []);
  const count = (genre: string, issuer: string) => options.documents[genre]?.[issuer] ?? 0;
  const genres = options.genres
    .map((genre) => ({
      ...genre,
      documents: options.issuers.reduce((sum, issuer) =>
        sum + (offIssuers.has(issuer.value) ? 0 : count(genre.value, issuer.value)), 0),
    }))
    .filter((genre) => genre.documents > 0);
  const issuers = options.issuers
    .map((issuer) => ({
      ...issuer,
      documents: options.genres.reduce((sum, genre) =>
        sum + (offGenres.has(genre.value) ? 0 : count(genre.value, issuer.value)), 0),
    }))
    .filter((issuer) => issuer.documents > 0);
  return { genres, issuers };
}

/**
 * A stored selection (a restored search, a guest's last search) read back as it was
 * sent: only selected collections that can be narrowed, and only string values. Values
 * the filter no longer lists are kept, so a selection is never read back broader than
 * it was searched. Undefined when nothing narrows.
 */
export function parseScopeSelections(
  value: unknown,
  collections: readonly string[],
): Record<string, ScopeSelection> | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return undefined;
  const scopes: Record<string, ScopeSelection> = {};
  for (const [collection, raw] of Object.entries(value as Record<string, unknown>)) {
    if (!scopeOptions(collection) || !collections.includes(collection)) continue;
    if (typeof raw !== "object" || raw === null) continue;
    const selection: ScopeSelection = {};
    for (const facet of ["genres", "issuers"] as const) {
      const values = (raw as Record<string, unknown>)[facet];
      if (!Array.isArray(values)) continue;
      const kept = [...new Set(values.filter((v): v is string => typeof v === "string"))];
      if (kept.length > 0) selection[facet] = kept;
    }
    if (selection.genres || selection.issuers) scopes[collection] = selection;
  }
  return Object.keys(scopes).length > 0 ? scopes : undefined;
}

function stringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const kept = [...new Set(value.filter((v): v is string => typeof v === "string"))];
  return kept.length > 0 ? kept : undefined;
}

/**
 * A stored request in today's vocabulary (5.1b.2): old collection keys become new ones,
 * and the old papal keys become a Papal documents genre selection, so a restored
 * "Encyclicals" search reopens as Papal documents with only encyclicals on.
 *
 * The genres searched are, for each old papal key, the genres its own stored selection
 * named (5.1a), or else the genres that key stands for; all three old keys without a
 * selection are the whole collection. Popes narrow only if every old papal key named
 * some, and then to all they named. A stored `papal` reads as itself, as the API drops
 * an old key beside its new one. Unknown keys are dropped; the caller decides what an
 * empty list means.
 */
export function canonicalSearchFilters(
  collections: readonly unknown[],
  scopes: unknown,
): { collections: string[]; scopes: Record<string, ScopeSelection> | undefined } {
  const keys = [...new Set(collections.filter((c): c is string => typeof c === "string"))];
  const stored = typeof scopes === "object" && scopes !== null && !Array.isArray(scopes)
    ? scopes as Record<string, unknown> : {};
  const selection = (key: string) => {
    const raw = stored[key];
    return typeof raw === "object" && raw !== null
      ? raw as Record<string, unknown> : {};
  };
  const oldPapal = keys.filter((key) => LEGACY_COLLECTIONS[key]?.key === "papal");
  const canonical = keys.map(canonicalCollectionKey);
  const out: Record<string, ScopeSelection> = {};

  // Selections of collections that were already new keys pass through unchanged.
  for (const key of keys) {
    if (key === canonicalCollectionKey(key) && scopeOptions(key)) {
      const genres = stringList(selection(key).genres);
      const issuers = stringList(selection(key).issuers);
      if (genres || issuers) out[key] = { ...(genres ? { genres } : {}), ...(issuers ? { issuers } : {}) };
    }
  }

  const papal = scopeOptions("papal");
  if (oldPapal.length > 0 && !keys.includes("papal") && papal) {
    const vocabulary = papal.genres.map((g) => g.value);
    const genres = new Set<string>();
    for (const key of oldPapal) {
      const legacy = LEGACY_COLLECTIONS[key];
      const named = stringList(selection(key).genres);
      const own = legacy.genres
        ?? vocabulary.filter((genre) => !legacy.withoutGenres?.includes(genre));
      for (const genre of named ?? own) genres.add(genre);
    }
    const issuerLists = oldPapal.map((key) => stringList(selection(key).issuers));
    const issuers = issuerLists.every((list) => list !== undefined)
      ? [...new Set(issuerLists.flat() as string[])] : undefined;
    const narrowed = vocabulary.some((genre) => !genres.has(genre));
    const entry: ScopeSelection = {
      ...(narrowed ? { genres: vocabulary.filter((genre) => genres.has(genre)) } : {}),
      ...(issuers ? { issuers } : {}),
    };
    if (entry.genres || entry.issuers) out.papal = entry;
  }

  return {
    collections: [...new Set(canonical)],
    scopes: Object.keys(out).length > 0 ? out : undefined,
  };
}
