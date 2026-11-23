import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  buildCollectionScopes,
  parseScopeSelections,
  visibleScopeValues,
  type CollectionScopeOptions,
  scopeGenreLabel,
  scopeIssuerLabel,
  type RegistryWork,
} from "./collection-scopes";

const WORKS = fileURLToPath(new URL("../../../../datapipeline/registry/works.json", import.meta.url));

describe("collection scopes", () => {
  it("is generated from the registry (run `npx vitest run -u collection-scopes` after a change)", async () => {
    const works = JSON.parse(readFileSync(WORKS, "utf8")) as RegistryWork[];
    const built = `${JSON.stringify(buildCollectionScopes(works), null, 1)}\n`;
    await expect(built).toMatchFileSnapshot("./collection-scopes.json");
  });

  it("labels genres as the cards do and popes without the title", () => {
    expect(scopeGenreLabel("apostolic-exhortation")).toBe("Apostolic exhortation");
    expect(scopeGenreLabel("motu-proprio")).toBe("Motu proprio");
    expect(scopeGenreLabel("other")).toBe("Other");
    expect(scopeIssuerLabel("Pope Leo XIII")).toBe("Leo XIII");
  });

  it("orders popes by pontificate and puts Other last", () => {
    const scopes = buildCollectionScopes([
      { collection: "papal", genre: "other", issuer: "pope-francis", issuer_label: "Pope Francis", year: 2015 },
      { collection: "papal", genre: "encyclical", issuer: "pope-leo-xiii", issuer_label: "Pope Leo XIII", year: 1891 },
      { collection: "papal", genre: "encyclical", issuer: "pope-leo-xiii", issuer_label: "Pope Leo XIII", year: 1879 },
      { collection: "papal", genre: null },
    ]);
    expect(scopes.papal.genres.map((g) => g.value)).toEqual(["encyclical", "other"]);
    expect(scopes.papal.issuers).toEqual([
      { value: "pope-leo-xiii", label: "Leo XIII" },
      { value: "pope-francis", label: "Francis" },
    ]);
    expect(scopes.papal.documents).toEqual({
      encyclical: { "pope-leo-xiii": 2 }, other: { "pope-francis": 1 },
    });
  });
});

describe("reading a stored selection back (restore)", () => {
  it("returns what a saved search sent, for collections it searched", () => {
    const saved = { papal: { genres: ["encyclical", "apostolic-letter"], issuers: ["pope-leo-xiii"] } };
    expect(parseScopeSelections(saved, ["papal", "bible"])).toEqual(saved);
  });

  it("drops other collections and bad shapes", () => {
    expect(parseScopeSelections({
      papal: { genres: ["encyclical", 7], issuers: "pope-leo-xiii" },
      bible: { genres: ["encyclical"] },
      "papal-documents": { genres: ["motu-proprio"] },
    }, ["papal", "bible"])).toEqual({ papal: { genres: ["encyclical"] } });
    expect(parseScopeSelections(null, ["papal"])).toBeUndefined();
    expect(parseScopeSelections(["papal"], ["papal"])).toBeUndefined();
  });

  it("never reads a selection back broader than it was searched", () => {
    // `letter` is a valid papal genre with no Encyclicals today; dropping it would read
    // "letters only" back as every Encyclical.
    expect(parseScopeSelections({ papal: { genres: ["letter"] } }, ["papal"]))
      .toEqual({ papal: { genres: ["letter"] } });
  });
});

describe("the lists follow each other's ticks", () => {
  const options: CollectionScopeOptions = {
    genres: [
      { value: "encyclical", label: "Encyclical" },
      { value: "apostolic-letter", label: "Apostolic letter" },
      { value: "motu-proprio", label: "Motu proprio" },
    ],
    issuers: [
      { value: "pope-leo-xiii", label: "Leo XIII" },
      { value: "pope-francis", label: "Francis" },
    ],
    documents: {
      encyclical: { "pope-leo-xiii": 7, "pope-francis": 4 },
      "apostolic-letter": { "pope-francis": 2 },
      "motu-proprio": { "pope-francis": 1 },
    },
  };
  const counts = (values: { value: string; documents: number }[]) =>
    Object.fromEntries(values.map((v) => [v.value, v.documents]));

  it("counts every document when nothing is unticked", () => {
    const shown = visibleScopeValues(options, undefined);
    expect(counts(shown.genres)).toEqual({ encyclical: 11, "apostolic-letter": 2, "motu-proprio": 1 });
    expect(counts(shown.issuers)).toEqual({ "pope-leo-xiii": 7, "pope-francis": 7 });
  });

  it("shows only the chosen pope's kinds, with his counts", () => {
    const shown = visibleScopeValues(options, { genres: [], issuers: ["pope-francis"] });
    expect(counts(shown.genres)).toEqual({ encyclical: 7 });
    // The Pope list is counted by kind, so it still offers Francis to tick back.
    expect(counts(shown.issuers)).toEqual({ "pope-leo-xiii": 7, "pope-francis": 7 });
  });

  it("shows only the popes who wrote the chosen kinds", () => {
    const shown = visibleScopeValues(options, { genres: ["encyclical"], issuers: [] });
    expect(counts(shown.issuers)).toEqual({ "pope-francis": 3 });
    expect(counts(shown.genres)).toEqual({ encyclical: 11, "apostolic-letter": 2, "motu-proprio": 1 });
  });
});
