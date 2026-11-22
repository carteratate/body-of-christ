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


describe("genre and issuer scopes (5.1a)", () => {
  const papal = () => createSearchDraft({
    preferred_translation: "CPDV",
    default_collections: ["encyclicals", "bible"],
    default_quota: 4,
    last_standard_quota: 4,
  });
  const genres = ["encyclical", "apostolic-letter", "apostolic-constitution", "apostolic-exhortation", "other"];

  it("searches everything until something is turned off", () => {
    const draft = papal();
    expect(draft.excluded).toEqual({});
    expect(draft.scopes).toBeUndefined();
  });

  it("turns one genre off and sends the rest", () => {
    const draft = transitionSearchDraft(papal(), { type: "genre-toggled", collection: "encyclicals", genre: "other" });
    expect(draft.excluded).toEqual({ encyclicals: { genres: ["other"], issuers: [] } });
    expect(draft.scopes).toEqual({ encyclicals: { genres: genres.filter((g) => g !== "other") } });
  });

  it("narrows to one with Only, adds a second, and returns to all", () => {
    let draft = transitionSearchDraft(papal(), {
      type: "scope-only", collection: "encyclicals", facet: "genres", value: "encyclical",
    });
    expect(draft.scopes).toEqual({ encyclicals: { genres: ["encyclical"] } });
    draft = transitionSearchDraft(draft, { type: "genre-toggled", collection: "encyclicals", genre: "apostolic-letter" });
    expect(draft.scopes).toEqual({ encyclicals: { genres: ["encyclical", "apostolic-letter"] } });
    draft = transitionSearchDraft(draft, { type: "scope-all", collection: "encyclicals", facet: "genres" });
    expect(draft.scopes).toBeUndefined();
    expect(draft.excluded).toEqual({});
  });

  it("keeps the last ticked value ticked", () => {
    const only = transitionSearchDraft(papal(), {
      type: "scope-only", collection: "encyclicals", facet: "genres", value: "encyclical",
    });
    expect(transitionSearchDraft(only, { type: "genre-toggled", collection: "encyclicals", genre: "encyclical" }))
      .toBe(only);
  });

  it("narrows genres and popes together", () => {
    let draft = transitionSearchDraft(papal(), {
      type: "scope-only", collection: "encyclicals", facet: "issuers", value: "pope-leo-xiii",
    });
    draft = transitionSearchDraft(draft, { type: "issuer-toggled", collection: "encyclicals", issuer: "pope-pius-ix" });
    draft = transitionSearchDraft(draft, { type: "genre-toggled", collection: "encyclicals", genre: "other" });
    expect(draft.scopes).toEqual({ encyclicals: {
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
    expect(transitionSearchDraft(draft, { type: "genre-toggled", collection: "encyclicals", genre: "sermon" }))
      .toBe(draft);
  });

  it("drops a collection's filter when it is deselected, and keeps it through other changes", () => {
    let draft = transitionSearchDraft(papal(), { type: "genre-toggled", collection: "encyclicals", genre: "other" });
    draft = transitionSearchDraft(draft, { type: "quota-selected", quota: 5 });
    draft = transitionSearchDraft(draft, { type: "translation-selected", translation: "douay-rheims" });
    expect(draft.excluded.encyclicals?.genres).toEqual(["other"]);
    draft = transitionSearchDraft(draft, { type: "collection-toggled", collection: "encyclicals" });
    expect(draft.scopes).toBeUndefined();
    draft = transitionSearchDraft(draft, { type: "collection-toggled", collection: "encyclicals" });
    expect(draft.scopes).toBeUndefined();
  });

  it("New Search clears every selection and keeps the rest of the draft", () => {
    let draft = transitionSearchDraft(papal(), { type: "genre-toggled", collection: "encyclicals", genre: "other" });
    draft = transitionSearchDraft(draft, { type: "quota-selected", quota: 5 });
    const cleared = transitionSearchDraft(draft, { type: "scopes-cleared" });
    expect(cleared.scopes).toBeUndefined();
    expect(cleared).toMatchObject({ collections: ["encyclicals", "bible"], quota: 5, translation: "CPDV" });
    expect(transitionSearchDraft(cleared, { type: "scopes-cleared" })).toBe(cleared);
  });

  it("a genre selection does not change focused eligibility", () => {
    let draft = createSearchDraft({
      preferred_translation: "CPDV", default_collections: ["encyclicals"], default_quota: 10, last_standard_quota: 4,
    });
    draft = transitionSearchDraft(draft, { type: "scope-only", collection: "encyclicals", facet: "genres", value: "encyclical" });
    expect(draft.quota).toBe(10);
    expect(draft.focusedEligible).toBe(true);
  });
});
