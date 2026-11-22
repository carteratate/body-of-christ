// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";

import { readGuestSearch } from "./useSearchPageExperience";

const KEY = "theocorpus-guest-current-results";

function stored(extra: Record<string, unknown>) {
  sessionStorage.setItem(KEY, JSON.stringify({
    savedAt: Date.now(),
    query: "What is a just wage?",
    passages: [],
    searchId: null,
    collections: ["encyclicals", "bible"],
    translation: "CPDV",
    quota: 4,
    visibleCollections: ["encyclicals", "bible"],
    outcome: null,
    collectionOutcomes: {},
    ...extra,
  }));
}

describe("a guest's last search keeps its genre and issuer selection (5.1a)", () => {
  afterEach(() => sessionStorage.clear());

  it("reads the stored selection back into the request", () => {
    stored({ scopes: { encyclicals: { genres: ["encyclical"], issuers: ["pope-leo-xiii"] } } });
    expect(readGuestSearch()?.continuity.request.scopes).toEqual({
      encyclicals: { genres: ["encyclical"], issuers: ["pope-leo-xiii"] },
    });
  });

  it("restores a search saved before scopes existed with none", () => {
    stored({});
    expect(readGuestSearch()?.continuity.request).not.toHaveProperty("scopes");
  });
});
