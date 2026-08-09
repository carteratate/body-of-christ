// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import { consumeReaderReturnKey, createReaderReturnKey } from "./readerNavigation";

beforeEach(() => sessionStorage.clear());

describe("reader return markers", () => {
  it("allows one same-origin return and then expires the marker", () => {
    const key = createReaderReturnKey("search");
    expect(key).toBeTruthy();
    expect(consumeReaderReturnKey(key, "search")).toBe(true);
    expect(consumeReaderReturnKey(key, "search")).toBe(false);
  });

  it("does not trust a marker for a different declared origin", () => {
    const key = createReaderReturnKey("saved");
    expect(key).toBeTruthy();
    expect(consumeReaderReturnKey(key, "search")).toBe(false);
  });
});
