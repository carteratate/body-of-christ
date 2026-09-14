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
