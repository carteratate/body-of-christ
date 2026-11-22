import type { SearchPreferenceDraft } from "./api";
import { scopeOptions, type ScopeFacet, type ScopeSelection } from "./collection-scopes";
import { ALL_COLLECTION_KEYS } from "./collections";


export type StandardQuota = 3 | 4 | 5;
export type SearchQuota = StandardQuota | 10;

export interface SearchDraftInitial {
  readonly preferred_translation?: unknown;
  readonly default_collections?: unknown;
  readonly default_quota?: unknown;
  readonly last_standard_quota?: unknown;
}

/** The values of one collection the user turned off, per facet (5.1a). */
export type ScopeExclusions = Readonly<Record<ScopeFacet, readonly string[]>>;

export interface SearchDraft {
  readonly collections: readonly string[];
  readonly translation: string;
  readonly quota: SearchQuota;
  readonly lastStandardQuota: StandardQuota;
  readonly focusedEligible: boolean;
  readonly preferences: SearchPreferenceDraft | null;
  /** Only selected collections the user narrowed; a genre selection is never a collection. */
  readonly excluded: Readonly<Record<string, ScopeExclusions>>;
  /** `filters.scopes` for the request: per narrowed collection, the values searched. */
  readonly scopes: Readonly<Record<string, ScopeSelection>> | undefined;
}

export type SearchDraftEvent =
  | { readonly type: "collection-toggled"; readonly collection: string }
  | { readonly type: "quota-selected"; readonly quota: SearchQuota }
  | { readonly type: "translation-selected"; readonly translation: string }
  | { readonly type: "genre-toggled"; readonly collection: string; readonly genre: string }
  | { readonly type: "issuer-toggled"; readonly collection: string; readonly issuer: string }
  | { readonly type: "scope-only"; readonly collection: string; readonly facet: ScopeFacet; readonly value: string }
  | { readonly type: "scope-all"; readonly collection: string; readonly facet: ScopeFacet }
  | { readonly type: "scopes-cleared" };

const VALID_TRANSLATIONS = new Set(["CPDV", "douay-rheims"]);
const STANDARD_QUOTAS = new Set<unknown>([3, 4, 5]);

export const DEFAULT_GUEST_SEARCH_PREFERENCES: SearchPreferenceDraft = {
  preferred_translation: "CPDV",
  default_collections: [
    "bible", "catechism", "church-fathers", "summa", "councils", "encyclicals",
  ],
  default_quota: 3,
  last_standard_quota: 3,
};

function isStandardQuota(value: unknown): value is StandardQuota {
  return STANDARD_QUOTAS.has(value);
}

function normalizeCollections(values: unknown): string[] {
  if (!Array.isArray(values)) return [...DEFAULT_GUEST_SEARCH_PREFERENCES.default_collections];
  const valid = values.filter(
    (value): value is string => typeof value === "string" && ALL_COLLECTION_KEYS.includes(value),
  );
  const unique = [...new Set(valid)];
  return unique.length > 0 ? unique : [...DEFAULT_GUEST_SEARCH_PREFERENCES.default_collections];
}

const NO_EXCLUSIONS: Readonly<Record<string, ScopeExclusions>> = Object.freeze({});

function scopeValues(collection: string, facet: ScopeFacet): string[] {
  return scopeOptions(collection)?.[facet].map((option) => option.value) ?? [];
}

function requestScopes(
  excluded: Readonly<Record<string, ScopeExclusions>>,
): Record<string, ScopeSelection> | undefined {
  const scopes: Record<string, ScopeSelection> = {};
  for (const [collection, off] of Object.entries(excluded)) {
    const selection: ScopeSelection = {};
    for (const facet of ["genres", "issuers"] as const) {
      if (off[facet].length > 0) {
        selection[facet] = scopeValues(collection, facet).filter((value) => !off[facet].includes(value));
      }
    }
    scopes[collection] = selection;
  }
  return Object.keys(scopes).length > 0 ? scopes : undefined;
}

function buildSearchDraft(
  collections: readonly string[],
  translation: string,
  quota: SearchQuota,
  lastStandardQuota: StandardQuota,
  excludedValues: Readonly<Record<string, ScopeExclusions>> = NO_EXCLUSIONS,
): SearchDraft {
  const collectionSnapshot = Object.freeze([...collections]);
  const focusedEligible = collectionSnapshot.length === 1;
  const preferences = collectionSnapshot.length === 0 ? null : Object.freeze({
    preferred_translation: translation,
    default_collections: [...collectionSnapshot],
    default_quota: quota,
    last_standard_quota: lastStandardQuota,
  });
  // A collection that is no longer selected keeps no hidden filter.
  const excluded = Object.freeze(Object.fromEntries(
    Object.entries(excludedValues)
      .filter(([collection, off]) => collectionSnapshot.includes(collection)
        && (off.genres.length > 0 || off.issuers.length > 0))
      .map(([collection, off]) => [collection, Object.freeze({
        genres: Object.freeze([...off.genres]),
        issuers: Object.freeze([...off.issuers]),
      })]),
  ));
  const scopes = requestScopes(excluded);
  return Object.freeze({
    collections: collectionSnapshot,
    translation,
    quota,
    lastStandardQuota,
    focusedEligible,
    preferences,
    excluded,
    scopes: scopes && Object.freeze(scopes),
  });
}

function withExclusions(draft: SearchDraft, collection: string, facet: ScopeFacet, off: readonly string[]): SearchDraft {
  const current = draft.excluded[collection] ?? { genres: [], issuers: [] };
  const sameSet = off.length === current[facet].length && off.every((value) => current[facet].includes(value));
  if (sameSet) return draft;
  return buildSearchDraft(
    draft.collections, draft.translation, draft.quota, draft.lastStandardQuota,
    { ...draft.excluded, [collection]: { ...current, [facet]: off } },
  );
}

/**
 * The scope rules: only a selected collection with that value can be narrowed, and at
 * least one value of each facet stays ticked, so a filter can never search nothing.
 */
function transitionScope(
  draft: SearchDraft,
  collection: string,
  facet: ScopeFacet,
  change: { readonly toggle: string } | { readonly only: string } | { readonly all: true },
): SearchDraft {
  if (!draft.collections.includes(collection)) return draft;
  const values = scopeValues(collection, facet);
  const off = draft.excluded[collection]?.[facet] ?? [];
  if ("all" in change) return withExclusions(draft, collection, facet, []);
  const value = "toggle" in change ? change.toggle : change.only;
  if (!values.includes(value)) return draft;
  if ("only" in change) {
    return withExclusions(draft, collection, facet, values.filter((other) => other !== value));
  }
  if (off.includes(value)) {
    return withExclusions(draft, collection, facet, off.filter((other) => other !== value));
  }
  if (off.length + 1 >= values.length) return draft;
  return withExclusions(draft, collection, facet, [...off, value]);
}

export function createSearchDraft(initial: SearchDraftInitial): SearchDraft {
  const collections = normalizeCollections(initial.default_collections);
  const translation = typeof initial.preferred_translation === "string"
    && VALID_TRANSLATIONS.has(initial.preferred_translation)
    ? initial.preferred_translation
    : "CPDV";
  let lastStandardQuota = isStandardQuota(initial.last_standard_quota)
    ? initial.last_standard_quota
    : isStandardQuota(initial.default_quota) ? initial.default_quota : 3;
  let quota: SearchQuota;
  if (initial.default_quota === 10 && collections.length === 1) {
    quota = 10;
  } else if (isStandardQuota(initial.default_quota)) {
    quota = initial.default_quota;
    lastStandardQuota = quota;
  } else {
    quota = lastStandardQuota;
  }
  return buildSearchDraft(collections, translation, quota, lastStandardQuota);
}

export function transitionSearchDraft(draft: SearchDraft, event: SearchDraftEvent): SearchDraft {
  switch (event.type) {
    case "genre-toggled":
      return transitionScope(draft, event.collection, "genres", { toggle: event.genre });
    case "issuer-toggled":
      return transitionScope(draft, event.collection, "issuers", { toggle: event.issuer });
    case "scope-only":
      return transitionScope(draft, event.collection, event.facet, { only: event.value });
    case "scope-all":
      return transitionScope(draft, event.collection, event.facet, { all: true });
    case "scopes-cleared":
      // New Search starts over: the filter is hidden behind the caret, so it must not
      // carry into the next question unseen. Collections, quota and translation stay.
      return draft.scopes === undefined
        ? draft
        : buildSearchDraft(draft.collections, draft.translation, draft.quota, draft.lastStandardQuota);
  }

  if (event.type === "collection-toggled") {
    if (!ALL_COLLECTION_KEYS.includes(event.collection)) return draft;
    const collections = draft.collections.includes(event.collection)
      ? draft.collections.filter((collection) => collection !== event.collection)
      : [...draft.collections, event.collection];
    const quota = draft.quota === 10 && collections.length !== 1
      ? draft.lastStandardQuota
      : draft.quota;
    return buildSearchDraft(
      collections, draft.translation, quota, draft.lastStandardQuota, draft.excluded);
  }

  if (event.type === "quota-selected") {
    if (event.quota === 10) {
      if (!draft.focusedEligible || draft.quota === 10) return draft;
      return buildSearchDraft(
        draft.collections, draft.translation, 10, draft.lastStandardQuota, draft.excluded);
    }
    if (draft.quota === event.quota && draft.lastStandardQuota === event.quota) return draft;
    return buildSearchDraft(
      draft.collections, draft.translation, event.quota, event.quota, draft.excluded);
  }

  if (!VALID_TRANSLATIONS.has(event.translation) || event.translation === draft.translation) return draft;
  return buildSearchDraft(
    draft.collections,
    event.translation,
    draft.quota,
    draft.lastStandardQuota,
    draft.excluded,
  );
}
