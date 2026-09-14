import type { SearchPreferenceDraft } from "./api";
import { ALL_COLLECTION_KEYS } from "./collections";


export type StandardQuota = 3 | 4 | 5;
export type SearchQuota = StandardQuota | 10;

export interface SearchDraftInitial {
  readonly preferred_translation?: unknown;
  readonly default_collections?: unknown;
  readonly default_quota?: unknown;
  readonly last_standard_quota?: unknown;
}

export interface SearchDraft {
  readonly collections: readonly string[];
  readonly translation: string;
  readonly quota: SearchQuota;
  readonly lastStandardQuota: StandardQuota;
  readonly focusedEligible: boolean;
  readonly preferences: SearchPreferenceDraft | null;
}

export type SearchDraftEvent =
  | { readonly type: "collection-toggled"; readonly collection: string }
  | { readonly type: "quota-selected"; readonly quota: SearchQuota }
  | { readonly type: "translation-selected"; readonly translation: string };

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

function buildSearchDraft(
  collections: readonly string[],
  translation: string,
  quota: SearchQuota,
  lastStandardQuota: StandardQuota,
): SearchDraft {
  const collectionSnapshot = Object.freeze([...collections]);
  const focusedEligible = collectionSnapshot.length === 1;
  const preferences = collectionSnapshot.length === 0 ? null : Object.freeze({
    preferred_translation: translation,
    default_collections: [...collectionSnapshot],
    default_quota: quota,
    last_standard_quota: lastStandardQuota,
  });
  return Object.freeze({
    collections: collectionSnapshot,
    translation,
    quota,
    lastStandardQuota,
    focusedEligible,
    preferences,
  });
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
  if (event.type === "collection-toggled") {
    if (!ALL_COLLECTION_KEYS.includes(event.collection)) return draft;
    const collections = draft.collections.includes(event.collection)
      ? draft.collections.filter((collection) => collection !== event.collection)
      : [...draft.collections, event.collection];
    const quota = draft.quota === 10 && collections.length !== 1
      ? draft.lastStandardQuota
      : draft.quota;
    return buildSearchDraft(collections, draft.translation, quota, draft.lastStandardQuota);
  }

  if (event.type === "quota-selected") {
    if (event.quota === 10) {
      if (!draft.focusedEligible || draft.quota === 10) return draft;
      return buildSearchDraft(draft.collections, draft.translation, 10, draft.lastStandardQuota);
    }
    if (draft.quota === event.quota && draft.lastStandardQuota === event.quota) return draft;
    return buildSearchDraft(draft.collections, draft.translation, event.quota, event.quota);
  }

  if (!VALID_TRANSLATIONS.has(event.translation) || event.translation === draft.translation) return draft;
  return buildSearchDraft(
    draft.collections,
    event.translation,
    draft.quota,
    draft.lastStandardQuota,
  );
}
