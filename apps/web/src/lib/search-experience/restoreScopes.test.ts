// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";

import type { SearchFilters } from "@/lib/api";
import { createSearchExperience } from "./runtime";
import type { SearchRequest } from "./types";
import { filtersFor, readGuestSearch, saveGuestSearch, savedSearchRequest } from "./useSearchPageExperience";

const SCOPES = { papal: { genres: ["encyclical", "apostolic-letter"], issuers: ["pope-leo-xiii"] } };
const FALLBACK = { translation: "CPDV", quota: 4 };

describe("a restored search keeps its genre and issuer selection (5.1a)", () => {
  it("reads it from the filters the API saved", () => {
    // `searches.filters` as services/api/app/rag/pipeline.py writes it.
    const filters = {
      collections: ["papal", "bible"], translation: "CPDV", quota: 5,
      outcome: "success", collection_outcomes: {}, scopes: SCOPES,
    };
    expect(savedSearchRequest({ query: "just wage", filters, results: [] }, FALLBACK)).toEqual({
      query: "just wage", collections: ["papal", "bible"], translation: "CPDV", quota: 5, scopes: SCOPES,
    });
  });

  it("restores a search saved without one, or before scopes existed, with none", () => {
    const request = savedSearchRequest({
      query: "grace", filters: { collections: ["papal"], translation: "CPDV", quota: 4 }, results: [],
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
      query: "just wage", collections: ["papal"], translation: "CPDV", quota: 4, scopes: SCOPES,
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
      request: { query: "just wage", collections: ["papal"], translation: "CPDV", quota: 4, scopes: SCOPES },
      searchId: null,
      passages: [],
      outcome: null,
      collectionOutcomes: {},
      deliveryOutcome: null,
      visibleCollections: ["papal"],
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

describe("a search saved with old collection keys reopens in today's (5.1b.2)", () => {
  const restore = (collections: string[], scopes?: unknown, results: { source: { collection: string } }[] = []) =>
    savedSearchRequest({
      query: "grace",
      filters: { collections, translation: "CPDV", quota: 4, ...(scopes ? { scopes } : {}) },
      results: results as never,
    }, FALLBACK);

  it("reopens an Encyclicals search as Papal documents with only encyclicals on", () => {
    expect(restore(["encyclicals", "bible"])).toEqual({
      query: "grace", collections: ["papal", "bible"], translation: "CPDV", quota: 4,
      scopes: { papal: { genres: ["encyclical"] } },
    });
  });

  it("joins several old papal keys, and all three are the whole collection", () => {
    expect(restore(["encyclicals", "apostolic-exhortations"]).scopes)
      .toEqual({ papal: { genres: ["encyclical", "apostolic-exhortation"] } });
    expect(restore(["papal-documents"]).scopes).toEqual({ papal: { genres: [
      "apostolic-letter", "apostolic-constitution", "motu-proprio", "other"] } });
    const all = restore(["encyclicals", "apostolic-exhortations", "papal-documents"]);
    expect(all.collections).toEqual(["papal"]);
    expect(all).not.toHaveProperty("scopes");
  });

  it("renames Canon law and Medieval without a selection", () => {
    const request = restore(["canon-law", "medieval", "summa"]);
    expect(request.collections).toEqual(["church-law", "theologians", "summa"]);
    expect(request).not.toHaveProperty("scopes");
  });

  it("keeps a 5.1a selection made under an old key", () => {
    expect(restore(["encyclicals"], { encyclicals: { genres: ["encyclical", "apostolic-letter"], issuers: ["pope-leo-xiii"] } }).scopes)
      .toEqual({ papal: { genres: ["encyclical", "apostolic-letter"], issuers: ["pope-leo-xiii"] } });
    // Popes narrow only if every old papal key named some.
    expect(restore(["encyclicals", "papal-documents"], { encyclicals: { issuers: ["pope-leo-xiii"] } }).scopes?.papal)
      .not.toHaveProperty("issuers");
  });

  it("falls back to its passages' collections, translated", () => {
    expect(restore([], undefined, [{ source: { collection: "medieval" } }, { source: { collection: "theologians" } }]).collections)
      .toEqual(["theologians"]);
  });
});

describe("old outcomes and passages read in today's keys (5.1b.2)", () => {
  it("merges the outcomes of old keys that became one collection", async () => {
    const { canonicalOutcomes } = await import("./useSearchPageExperience");
    expect(canonicalOutcomes({ encyclicals: "results", "papal-documents": "no_candidates", "canon-law": "below_threshold" }))
      .toEqual({ papal: "results", "church-law": "below_threshold" });
    expect(canonicalOutcomes({ encyclicals: "results", "apostolic-exhortations": "retrieval_failed" }))
      .toEqual({ papal: "results_degraded" });
    expect(canonicalOutcomes({ encyclicals: "no_candidates", "apostolic-exhortations": "below_threshold" }))
      .toEqual({ papal: "below_threshold" });
    expect(canonicalOutcomes(null)).toBeNull();
  });

  it("labels a passage with its new key", async () => {
    const { canonicalPassage } = await import("./useSearchPageExperience");
    const passage = { chunk_id: "c", source: { collection: "encyclicals", document_title: "Rerum Novarum" } };
    expect(canonicalPassage(passage).source).toEqual({ collection: "papal", document_title: "Rerum Novarum" });
    const current = { source: { collection: "summa" } };
    expect(canonicalPassage(current)).toBe(current);
  });

  it("reads a guest's last search saved before the switch", () => {
    sessionStorage.setItem("theocorpus-guest-current-results", JSON.stringify({
      savedAt: Date.now(), query: "grace", passages: [{ chunk_id: "c", source: { collection: "canon-law" } }],
      collections: ["encyclicals", "canon-law"], translation: "CPDV", quota: 4,
      visibleCollections: ["encyclicals", "canon-law"], outcome: "success",
      collectionOutcomes: { encyclicals: "results", "canon-law": "results" },
    }));
    const restored = readGuestSearch();
    expect(restored?.continuity.request).toMatchObject({
      collections: ["papal", "church-law"], scopes: { papal: { genres: ["encyclical"] } },
    });
    expect(restored?.visibleCollections).toEqual(["papal", "church-law"]);
    expect(restored?.continuity.passages[0].source.collection).toBe("church-law");
    expect(restored?.continuity.collectionOutcomes).toEqual({ papal: "results", "church-law": "results" });
  });

  it("falls back to its passages' collections when no stored key is known", () => {
    sessionStorage.setItem("theocorpus-guest-current-results", JSON.stringify({
      savedAt: Date.now(), query: "grace", passages: [{ chunk_id: "c", source: { collection: "medieval" } }],
      collections: ["saints"], translation: "CPDV", quota: 4, visibleCollections: [], outcome: "success",
      collectionOutcomes: {},
    }));
    expect(readGuestSearch()?.continuity.request.collections).toEqual(["theologians"]);
  });
});
