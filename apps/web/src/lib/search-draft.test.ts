import { describe, expect, it } from "vitest";

import { createSearchDraft, transitionSearchDraft } from "./search-draft";


const focusedPreferences = {
  preferred_translation: "CPDV",
  default_collections: ["bible"],
  default_quota: 10,
  last_standard_quota: 5 as const,
};


describe("search draft", () => {
  it("restores a valid focused default", () => {
    const draft = createSearchDraft(focusedPreferences);

    expect(draft).toEqual(expect.objectContaining({
      collections: ["bible"],
      quota: 10,
      lastStandardQuota: 5,
      focusedEligible: true,
      preferences: focusedPreferences,
    }));
  });

  it.each([3, 4, 5] as const)("selecting %s updates quota and last standard quota", (quota) => {
    const draft = transitionSearchDraft(
      createSearchDraft(focusedPreferences),
      { type: "quota-selected", quota },
    );

    expect(draft.quota).toBe(quota);
    expect(draft.lastStandardQuota).toBe(quota);
    expect(draft.preferences?.last_standard_quota).toBe(quota);
  });

  it("selects 10 only when exactly one collection is active", () => {
    const standard = createSearchDraft({
      ...focusedPreferences,
      default_collections: ["bible", "catechism"],
      default_quota: 5,
    });

    expect(transitionSearchDraft(standard, { type: "quota-selected", quota: 10 })).toBe(standard);

    const eligible = transitionSearchDraft(standard, { type: "collection-toggled", collection: "catechism" });
    const focused = transitionSearchDraft(eligible, { type: "quota-selected", quota: 10 });
    expect(focused.quota).toBe(10);
    expect(focused.lastStandardQuota).toBe(5);
  });

  it("restores the last standard quota when a collection is added in focused mode", () => {
    const next = transitionSearchDraft(
      createSearchDraft(focusedPreferences),
      { type: "collection-toggled", collection: "catechism" },
    );

    expect(next.collections).toEqual(["bible", "catechism"]);
    expect(next.quota).toBe(5);
    expect(next.lastStandardQuota).toBe(5);
    expect(next.focusedEligible).toBe(false);
  });

  it("reveals focused eligibility without reactivating 10 after returning to one collection", () => {
    const multiple = transitionSearchDraft(
      createSearchDraft(focusedPreferences),
      { type: "collection-toggled", collection: "catechism" },
    );
    const single = transitionSearchDraft(
      multiple,
      { type: "collection-toggled", collection: "catechism" },
    );

    expect(single.focusedEligible).toBe(true);
    expect(single.quota).toBe(5);
  });

  it("allows an empty working selection but withholds an invalid preference snapshot", () => {
    const empty = transitionSearchDraft(
      createSearchDraft(focusedPreferences),
      { type: "collection-toggled", collection: "bible" },
    );

    expect(empty.collections).toEqual([]);
    expect(empty.focusedEligible).toBe(false);
    expect(empty.preferences).toBeNull();
  });

  it("normalizes invalid and historical preference combinations safely", () => {
    const draft = createSearchDraft({
      preferred_translation: "obsolete",
      default_collections: ["bible", "retired", "bible"],
      default_quota: 10,
      last_standard_quota: 4,
    });

    expect(draft).toEqual(expect.objectContaining({
      collections: ["bible"],
      translation: "CPDV",
      quota: 10,
      lastStandardQuota: 4,
    }));

    const incompatible = createSearchDraft({
      ...focusedPreferences,
      default_collections: ["bible", "catechism"],
    });
    expect(incompatible.quota).toBe(5);
  });

  it("ignores unknown collection events", () => {
    const draft = createSearchDraft(focusedPreferences);
    expect(transitionSearchDraft(
      draft,
      { type: "collection-toggled", collection: "retired" },
    )).toBe(draft);
  });

  it("returns new collection arrays so submitted snapshots remain immutable", () => {
    const draft = createSearchDraft(focusedPreferences);
    const submitted = [...draft.collections];
    const changed = transitionSearchDraft(
      draft,
      { type: "collection-toggled", collection: "catechism" },
    );

    expect(submitted).toEqual(["bible"]);
    expect(changed.collections).not.toBe(draft.collections);
  });
});


describe("old collection keys in saved preferences (5.1b.2)", () => {
  it("reads them as today's keys, once each", () => {
    const draft = createSearchDraft({
      preferred_translation: "CPDV",
      default_collections: ["encyclicals", "apostolic-exhortations", "canon-law", "medieval", "bible", "saints"],
      default_quota: 4,
      last_standard_quota: 4,
    });
    expect(draft.collections).toEqual(["papal", "church-law", "theologians", "bible"]);
    expect(draft.scopes).toBeUndefined();
  });

  it("keeps a focused preference focused on the new key", () => {
    const draft = createSearchDraft({
      preferred_translation: "CPDV", default_collections: ["canon-law"], default_quota: 10, last_standard_quota: 3,
    });
    expect(draft).toMatchObject({ collections: ["church-law"], quota: 10 });
  });
});

describe("genre and issuer scopes (5.1a)", () => {
  const papal = () => createSearchDraft({
    preferred_translation: "CPDV",
    default_collections: ["papal", "bible"],
    default_quota: 4,
    last_standard_quota: 4,
  });
  const genres = ["encyclical", "apostolic-exhortation", "apostolic-letter", "apostolic-constitution", "motu-proprio", "other"];

  it("searches everything until something is turned off", () => {
    const draft = papal();
    expect(draft.excluded).toEqual({});
    expect(draft.scopes).toBeUndefined();
  });

  it("turns one genre off and sends the rest", () => {
    const draft = transitionSearchDraft(papal(), { type: "genre-toggled", collection: "papal", genre: "other" });
    expect(draft.excluded).toEqual({ papal: { genres: ["other"], issuers: [], documents: [] } });
    expect(draft.scopes).toEqual({ papal: { genres: genres.filter((g) => g !== "other") } });
  });

  it("narrows to one with Only, adds a second, and returns to all", () => {
    let draft = transitionSearchDraft(papal(), {
      type: "scope-only", collection: "papal", facet: "genres", value: "encyclical",
    });
    expect(draft.scopes).toEqual({ papal: { genres: ["encyclical"] } });
    draft = transitionSearchDraft(draft, { type: "genre-toggled", collection: "papal", genre: "apostolic-letter" });
    expect(draft.scopes).toEqual({ papal: { genres: ["encyclical", "apostolic-letter"] } });
    draft = transitionSearchDraft(draft, { type: "scope-all", collection: "papal", facet: "genres" });
    expect(draft.scopes).toBeUndefined();
    expect(draft.excluded).toEqual({});
  });

  it("keeps the last ticked value ticked", () => {
    const only = transitionSearchDraft(papal(), {
      type: "scope-only", collection: "papal", facet: "genres", value: "encyclical",
    });
    expect(transitionSearchDraft(only, { type: "genre-toggled", collection: "papal", genre: "encyclical" }))
      .toBe(only);
  });

  it("narrows genres and popes together", () => {
    let draft = transitionSearchDraft(papal(), {
      type: "scope-only", collection: "papal", facet: "issuers", value: "pope-leo-xiii",
    });
    draft = transitionSearchDraft(draft, { type: "issuer-toggled", collection: "papal", issuer: "pope-pius-ix" });
    draft = transitionSearchDraft(draft, { type: "genre-toggled", collection: "papal", genre: "other" });
    expect(draft.scopes).toEqual({ papal: {
      genres: genres.filter((g) => g !== "other"),
      issuers: ["pope-pius-ix", "pope-leo-xiii"],
    } });
  });

  it("ignores collections that are not selected or have no such value", () => {
    const draft = papal();
    expect(transitionSearchDraft(draft, { type: "genre-toggled", collection: "papal-documents", genre: "motu-proprio" }))
      .toBe(draft);
    expect(transitionSearchDraft(draft, { type: "genre-toggled", collection: "bible", genre: "encyclical" }))
      .toBe(draft);
    expect(transitionSearchDraft(draft, { type: "genre-toggled", collection: "papal", genre: "sermon" }))
      .toBe(draft);
  });

  it("drops a collection's filter when it is deselected, and keeps it through other changes", () => {
    let draft = transitionSearchDraft(papal(), { type: "genre-toggled", collection: "papal", genre: "other" });
    draft = transitionSearchDraft(draft, { type: "quota-selected", quota: 5 });
    draft = transitionSearchDraft(draft, { type: "translation-selected", translation: "douay-rheims" });
    expect(draft.excluded.papal?.genres).toEqual(["other"]);
    draft = transitionSearchDraft(draft, { type: "collection-toggled", collection: "papal" });
    expect(draft.scopes).toBeUndefined();
    draft = transitionSearchDraft(draft, { type: "collection-toggled", collection: "papal" });
    expect(draft.scopes).toBeUndefined();
  });

  it("New Search clears every selection and keeps the rest of the draft", () => {
    let draft = transitionSearchDraft(papal(), { type: "genre-toggled", collection: "papal", genre: "other" });
    draft = transitionSearchDraft(draft, { type: "quota-selected", quota: 5 });
    const cleared = transitionSearchDraft(draft, { type: "scopes-cleared" });
    expect(cleared.scopes).toBeUndefined();
    expect(cleared).toMatchObject({ collections: ["papal", "bible"], quota: 5, translation: "CPDV" });
    expect(transitionSearchDraft(cleared, { type: "scopes-cleared" })).toBe(cleared);
  });

  it("a genre selection does not change focused eligibility", () => {
    let draft = createSearchDraft({
      preferred_translation: "CPDV", default_collections: ["papal"], default_quota: 10, last_standard_quota: 4,
    });
    draft = transitionSearchDraft(draft, { type: "scope-only", collection: "papal", facet: "genres", value: "encyclical" });
    expect(draft.quota).toBe(10);
    expect(draft.focusedEligible).toBe(true);
  });
});

describe("work scopes (Catechism)", () => {
  const CCC = "9679c400-d314-5394-b916-f6fc27b50104";
  const COMPENDIUM = "800373b1-d6c8-5a26-8910-8d1485b224c2";
  const ROMAN = "c6d78d5e-5f23-5f86-b0ca-97a741e186bf";
  const catechism = () => createSearchDraft({
    preferred_translation: "CPDV", default_collections: ["catechism", "bible"],
    default_quota: 4, last_standard_quota: 4,
  });

  it("turns one work off and sends the others, by document", () => {
    const draft = transitionSearchDraft(catechism(), { type: "document-toggled", collection: "catechism", document: ROMAN });
    expect(draft.excluded).toEqual({ catechism: { genres: [], issuers: [], documents: [ROMAN] } });
    expect(draft.scopes).toEqual({ catechism: { documents: [CCC, COMPENDIUM] } });
  });

  it("keeps one work ticked, and ignores a document the collection does not list", () => {
    const only = transitionSearchDraft(catechism(), {
      type: "scope-only", collection: "catechism", facet: "documents", value: CCC,
    });
    expect(only.scopes).toEqual({ catechism: { documents: [CCC] } });
    expect(transitionSearchDraft(only, { type: "document-toggled", collection: "catechism", document: CCC })).toBe(only);
    expect(transitionSearchDraft(only, { type: "document-toggled", collection: "catechism", document: "nope" })).toBe(only);
  });

  it("offers no work filter on a collection without one, and no genre filter on the Catechism", () => {
    const papal = createSearchDraft({ default_collections: ["papal", "catechism"], default_quota: 4 });
    expect(transitionSearchDraft(papal, { type: "document-toggled", collection: "papal", document: CCC })).toBe(papal);
    expect(transitionSearchDraft(papal, { type: "genre-toggled", collection: "catechism", genre: "catechism" })).toBe(papal);
  });

  it("drops the work filter when the Catechism is deselected, and leaves focused eligibility alone", () => {
    let draft = createSearchDraft({ default_collections: ["catechism"], default_quota: 10 });
    draft = transitionSearchDraft(draft, { type: "document-toggled", collection: "catechism", document: ROMAN });
    expect(draft.quota).toBe(10);
    expect(draft.focusedEligible).toBe(true);
    draft = transitionSearchDraft(draft, { type: "collection-toggled", collection: "bible" });
    draft = transitionSearchDraft(draft, { type: "collection-toggled", collection: "catechism" });
    expect(draft.scopes).toBeUndefined();
  });
});
