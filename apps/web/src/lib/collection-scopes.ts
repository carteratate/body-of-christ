import { genreLabel } from "./attribution";
import data from "./collection-scopes.json";

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
  readonly documents: number;
}

export interface CollectionScopeOptions {
  readonly genres: readonly ScopeValue[];
  readonly issuers: readonly ScopeValue[];
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
export const SCOPED_COLLECTIONS = ["encyclicals", "apostolic-exhortations", "papal-documents"] as const;

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
    const issuers = new Map<string, { label: string; documents: number; first: number }>();
    for (const work of works) {
      // A work without a genre is not published (held for permission).
      if (work.collection !== collection || !work.genre) continue;
      genres.set(work.genre, (genres.get(work.genre) ?? 0) + 1);
      if (work.issuer && work.issuer_label) {
        const seen = issuers.get(work.issuer);
        const year = work.year ?? Number.MAX_SAFE_INTEGER;
        issuers.set(work.issuer, {
          label: work.issuer_label,
          documents: (seen?.documents ?? 0) + 1,
          first: Math.min(seen?.first ?? Number.MAX_SAFE_INTEGER, year),
        });
      }
    }
    out[collection] = {
      // Most documents first; "other" always last.
      genres: [...genres]
        .sort(([a, an], [b, bn]) =>
          Number(a === "other") - Number(b === "other") || bn - an || a.localeCompare(b))
        .map(([value, documents]) => ({ value, label: scopeGenreLabel(value), documents })),
      // Popes in the order of their first document here: the order of their pontificates.
      issuers: [...issuers]
        .sort(([, a], [, b]) => a.first - b.first)
        .map(([value, { label, documents }]) => ({
          value, label: scopeIssuerLabel(label), documents,
        })),
    };
  }
  return out;
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
