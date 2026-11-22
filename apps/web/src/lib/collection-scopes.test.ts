import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  COLLECTION_SCOPES,
  SCOPED_COLLECTIONS,
  buildCollectionScopes,
  parseScopeSelections,
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

  it("covers exactly the collections the API can narrow", () => {
    expect(Object.keys(COLLECTION_SCOPES).sort()).toEqual([...SCOPED_COLLECTIONS].sort());
  });

  it("labels genres as the cards do and popes without the title", () => {
    expect(scopeGenreLabel("apostolic-exhortation")).toBe("Apostolic exhortation");
    expect(scopeGenreLabel("motu-proprio")).toBe("Motu proprio");
    expect(scopeGenreLabel("other")).toBe("Other");
    expect(scopeIssuerLabel("Pope Leo XIII")).toBe("Leo XIII");
  });

  it("orders popes by pontificate and puts Other last", () => {
    const scopes = buildCollectionScopes([
      { collection: "encyclicals", genre: "other", issuer: "pope-francis", issuer_label: "Pope Francis", year: 2015 },
      { collection: "encyclicals", genre: "encyclical", issuer: "pope-leo-xiii", issuer_label: "Pope Leo XIII", year: 1891 },
      { collection: "encyclicals", genre: "encyclical", issuer: "pope-leo-xiii", issuer_label: "Pope Leo XIII", year: 1879 },
      { collection: "encyclicals", genre: null },
    ]);
    expect(scopes.encyclicals.genres.map((g) => g.value)).toEqual(["encyclical", "other"]);
    expect(scopes.encyclicals.issuers).toEqual([
      { value: "pope-leo-xiii", label: "Leo XIII", documents: 2 },
      { value: "pope-francis", label: "Francis", documents: 1 },
    ]);
  });
});

describe("reading a stored selection back (restore)", () => {
  it("returns what a saved search sent, for collections it searched", () => {
    const saved = { encyclicals: { genres: ["encyclical", "apostolic-letter"], issuers: ["pope-leo-xiii"] } };
    expect(parseScopeSelections(saved, ["encyclicals", "bible"])).toEqual(saved);
  });

  it("drops what the filter cannot show: other collections, unknown values, bad shapes", () => {
    expect(parseScopeSelections({
      encyclicals: { genres: ["encyclical", "sermon"], issuers: "pope-leo-xiii" },
      bible: { genres: ["encyclical"] },
      "papal-documents": { genres: ["motu-proprio"] },
    }, ["encyclicals", "bible"])).toEqual({ encyclicals: { genres: ["encyclical"] } });
    expect(parseScopeSelections(null, ["encyclicals"])).toBeUndefined();
    expect(parseScopeSelections(["encyclicals"], ["encyclicals"])).toBeUndefined();
    expect(parseScopeSelections({ encyclicals: { genres: ["sermon"] } }, ["encyclicals"])).toBeUndefined();
  });
});
