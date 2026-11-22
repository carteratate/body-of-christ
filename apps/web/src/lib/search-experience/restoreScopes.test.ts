// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";

import type { SearchFilters } from "@/lib/api";
import { createSearchExperience } from "./runtime";
import type { SearchRequest } from "./types";
import { filtersFor, readGuestSearch, saveGuestSearch, savedSearchRequest } from "./useSearchPageExperience";

const SCOPES = { encyclicals: { genres: ["encyclical", "apostolic-letter"], issuers: ["pope-leo-xiii"] } };
const FALLBACK = { translation: "CPDV", quota: 4 };

describe("a restored search keeps its genre and issuer selection (5.1a)", () => {
  it("reads it from the filters the API saved", () => {
    // `searches.filters` as services/api/app/rag/pipeline.py writes it.
    const filters = {
      collections: ["encyclicals", "bible"], translation: "CPDV", quota: 5,
      outcome: "success", collection_outcomes: {}, scopes: SCOPES,
    };
    expect(savedSearchRequest({ query: "just wage", filters, results: [] }, FALLBACK)).toEqual({
      query: "just wage", collections: ["encyclicals", "bible"], translation: "CPDV", quota: 5, scopes: SCOPES,
    });
  });

  it("restores a search saved without one, or before scopes existed, with none", () => {
    const request = savedSearchRequest({
      query: "grace", filters: { collections: ["encyclicals"], translation: "CPDV", quota: 4 }, results: [],
    }, FALLBACK);
    expect(request).not.toHaveProperty("scopes");
  });
});

describe("a signed-in search's selection survives submit, save and restore (5.1a)", () => {
  it("restores the selection the search was sent with", async () => {
    const sent: SearchFilters[] = [];
    const runtime = createSearchExperience({
      audience: {
        kind: "authenticated",
        async search(_credential, request) {
          sent.push(filtersFor(request));
        },
      },
      credentials: { current: () => "token" },
      savedSearch: {
        // The API stores the submitted filters (plus outcomes) and returns them on restore.
        async restore() {
          const stored = { ...sent[0], quota: 4, outcome: "success", collection_outcomes: {} };
          return {
            searchId: "saved",
            request: savedSearchRequest({ query: "just wage", filters: stored, results: [] }, FALLBACK),
            passages: [],
            warning: null,
          };
        },
        classifyFailure: () => ({ message: "failed", code: "unknown", stage: "restore", retryable: false }),
      },
    });
    const request: SearchRequest = {
      query: "just wage", collections: ["encyclicals"], translation: "CPDV", quota: 4, scopes: SCOPES,
    };

    runtime.send({ type: "submit", request });
    expect(sent[0].scopes).toEqual(SCOPES);
    runtime.send({ type: "restore", searchId: "saved" });
    await new Promise((resolve) => setTimeout(resolve, 0));

    const snapshot = runtime.read();
    expect(snapshot.status).toBe("restored-passages");
    if (snapshot.status !== "restored-passages") return;
    expect(snapshot.request.scopes).toEqual(SCOPES);
  });
});

describe("a guest's last search keeps its selection (5.1a)", () => {
  afterEach(() => sessionStorage.clear());

  it("survives a save and a read", () => {
    saveGuestSearch({
      savedAt: Date.now(),
      request: { query: "just wage", collections: ["encyclicals"], translation: "CPDV", quota: 4, scopes: SCOPES },
      searchId: null,
      passages: [],
      outcome: null,
      collectionOutcomes: {},
      deliveryOutcome: null,
      visibleCollections: ["encyclicals"],
    });
    expect(readGuestSearch()?.continuity.request.scopes).toEqual(SCOPES);
  });

  it("restores a search saved before scopes existed with none", () => {
    saveGuestSearch({
      savedAt: Date.now(),
      request: { query: "grace", collections: ["bible"], translation: "CPDV", quota: 4 },
      searchId: null,
      passages: [],
      outcome: null,
      collectionOutcomes: {},
      deliveryOutcome: null,
      visibleCollections: ["bible"],
    });
    expect(readGuestSearch()?.continuity.request).not.toHaveProperty("scopes");
  });
});
