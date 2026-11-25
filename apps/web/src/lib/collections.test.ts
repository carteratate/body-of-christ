import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  ALL_COLLECTION_KEYS, canonicalCollectionKey, canonicalDocuments, getCollectionMeta, LEGACY_COLLECTIONS,
} from "./collections";

const CONSTANTS = fileURLToPath(new URL("../../../../services/api/app/rag/constants.py", import.meta.url));

describe("collection keys after 5.1b", () => {
  it("offers the API's canonical collections", () => {
    const source = readFileSync(CONSTANTS, "utf8");
    const block = source.slice(source.indexOf("CANONICAL_COLLECTIONS"), source.indexOf("})"));
    const api = [...block.matchAll(/"([a-z-]+)"/g)].map((m) => m[1]);
    expect([...ALL_COLLECTION_KEYS].sort()).toEqual(api.sort());
  });

  it("maps each old key a browser may hold to its new collection", () => {
    expect(Object.fromEntries(Object.entries(LEGACY_COLLECTIONS).map(([k, v]) => [k, v.key]))).toEqual({
      encyclicals: "papal", "apostolic-exhortations": "papal", "papal-documents": "papal",
      "canon-law": "church-law", medieval: "theologians",
    });
    expect(canonicalCollectionKey("summa")).toBe("summa");
    expect(canonicalCollectionKey("constructor")).toBe("constructor");
  });

  it("gives an old stored key its new name and colour", () => {
    expect(getCollectionMeta("encyclicals")).toEqual(getCollectionMeta("papal"));
    expect(getCollectionMeta("encyclicals")?.label).toBe("Papal documents");
    expect(getCollectionMeta("canon-law")?.label).toBe("Church law");
    expect(getCollectionMeta("medieval")?.label).toBe("Theology & Spirituality");
    expect(getCollectionMeta("saints")).toBeUndefined();
  });

  it("reads documents in new keys, ordered as the API orders them", () => {
    const docs = canonicalDocuments([
      { collection: "summa", year: 1274, title: "Summa" },
      { collection: "papal-documents", year: 1302, title: "Unam Sanctam" },
      { collection: "encyclicals", year: null, title: "Undated" },
      { collection: "encyclicals", year: 1891, title: "Rerum Novarum" },
    ]);
    expect(docs.map((d) => [d.collection, d.title])).toEqual([
      ["papal", "Unam Sanctam"], ["papal", "Rerum Novarum"], ["papal", "Undated"], ["summa", "Summa"],
    ]);
  });
});
