import { describe, expect, it } from "vitest";

import { ALL_COLLECTION_KEYS, COLLECTIONS, getCollectionMeta } from "./collections";

describe("collections", () => {
  it("does not offer an unreleased collection", () => {
    expect(COLLECTIONS.map((c) => c.key)).not.toContain("roman-curia");
    expect(ALL_COLLECTION_KEYS).not.toContain("roman-curia");
  });

  it("still labels an unreleased collection wherever a stored result names it", () => {
    expect(getCollectionMeta("roman-curia")).toMatchObject({
      label: "Roman Curia",
      color: "var(--color-collection-roman-curia)",
    });
  });

  it("returns nothing for an unknown key", () => {
    expect(getCollectionMeta("not-a-collection")).toBeUndefined();
  });
});
