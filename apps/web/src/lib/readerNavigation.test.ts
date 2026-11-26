// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  readerSectionCollection,
  consumeReaderReturnKey,
  hasReaderReturnMarker,
  markReaderReturn,
  newReaderReturnKey,
  readerHref,
} from "./readerNavigation";

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.useRealTimers());

describe("reader return markers", () => {
  it("allows one same-origin return and then expires the marker", () => {
    const key = newReaderReturnKey();
    expect(key).toBeTruthy();
    markReaderReturn(key, "search");
    expect(consumeReaderReturnKey(key, "search")).toBe(true);
    expect(consumeReaderReturnKey(key, "search")).toBe(false);
  });

  it("does not trust a marker for a different declared origin", () => {
    const key = newReaderReturnKey();
    markReaderReturn(key, "saved");
    expect(consumeReaderReturnKey(key, "search")).toBe(false);
  });

  it("finds no marker for a key that was made but never navigated through", () => {
    // A link's key exists from render; only a same-tab navigation marks it.
    const key = newReaderReturnKey();
    expect(hasReaderReturnMarker(key, "library")).toBe(false);
    expect(consumeReaderReturnKey(key, "library")).toBe(false);
  });

  it("peeks without using the marker up", () => {
    const key = newReaderReturnKey();
    markReaderReturn(key, "library");
    expect(hasReaderReturnMarker(key, "library")).toBe(true);
    expect(hasReaderReturnMarker(key, "library")).toBe(true);
    expect(hasReaderReturnMarker(key, "saved")).toBe(false);
    expect(consumeReaderReturnKey(key, "library")).toBe(true);
    expect(hasReaderReturnMarker(key, "library")).toBe(false);
  });

  it("expires a marker after two hours", () => {
    vi.useFakeTimers({ now: new Date("2026-10-12T10:00:00Z") });
    const key = newReaderReturnKey();
    markReaderReturn(key, "search");
    vi.setSystemTime(new Date("2026-10-12T12:00:01Z"));
    expect(hasReaderReturnMarker(key, "search")).toBe(false);
  });

  it("ignores a key that isn't a UUID", () => {
    markReaderReturn("not-a-key", "search");
    expect(sessionStorage.length).toBe(0);
    expect(consumeReaderReturnKey("not-a-key", "search")).toBe(false);
  });
});

describe("readerHref", () => {
  const key = "11111111-1111-4111-8111-111111111111";

  it("builds the signed-in reader URL in a fixed param order", () => {
    expect(readerHref({ docId: "doc-a", origin: "search", returnKey: key, anchor: "p-3", chapter: "c-1" }))
      .toBe(`/reader/doc-a?from=search&returnKey=${key}&anchor=p-3`);
    expect(readerHref({ docId: "doc-a", origin: "library", returnKey: key, chapter: "c-1" }))
      .toBe(`/reader/doc-a?from=library&returnKey=${key}&chapter=c-1`);
    expect(readerHref({ docId: "doc-a", origin: "saved", returnKey: null }))
      .toBe("/reader/doc-a?from=saved");
  });

  it("encodes the document id as one path segment", () => {
    expect(readerHref({ docId: "../../login?next=x#y", origin: "library", returnKey: null }))
      .toBe("/reader/..%2F..%2Flogin%3Fnext%3Dx%23y?from=library");
  });

  it("adds guest params only for the guest reader", () => {
    expect(readerHref({ docId: "doc-a", origin: "search", returnKey: key, anchor: "p-3", guest: true, guideBack: true, preview: true }))
      .toBe(`/reader/guest/doc-a?from=search&returnKey=${key}&anchor=p-3&guideBack=1&preview=1`);
    expect(readerHref({ docId: "doc-a", origin: "search", returnKey: key, guideBack: true, preview: true }))
      .toBe(`/reader/doc-a?from=search&returnKey=${key}`);
  });
});

describe("retired anchors (corpus cleanup 2.4a)", () => {
  // 2.2w keeps a retired passage's anchor as `<anchor>#retired-<release>` when a current
  // passage takes it. The `#` must reach the reader as part of the anchor, not as a
  // URL fragment.
  const anchor = "c1/p2#retired-rel-1";

  it("encodes the # as %23 so it is not read as a fragment", () => {
    const href = readerHref({ docId: "doc-a", origin: "saved", returnKey: null, anchor });
    expect(href).toBe("/reader/doc-a?from=saved&anchor=c1%2Fp2%23retired-rel-1");
    const url = new URL(href, "https://theo-corpus.com");
    expect(url.hash).toBe("");
    expect(url.searchParams.get("anchor")).toBe(anchor);
  });

  it("does the same for the guest reader", () => {
    const href = readerHref({ docId: "doc-a", origin: "search", returnKey: null, anchor, guest: true });
    expect(new URL(href, "https://theo-corpus.com").searchParams.get("anchor")).toBe(anchor);
  });
});

describe("readerSectionCollection", () => {
  it("keeps the paragraph-range wording for the Catechism of the Catholic Church only", () => {
    expect(readerSectionCollection({ collection: "catechism", title: "Catechism of the Catholic Church" })).toBe("catechism");
    expect(readerSectionCollection({ collection: "catechism", title: "Catechism of the Council of Trent" })).toBe("");
    expect(readerSectionCollection({ collection: "summa", title: "Summa Theologiae" })).toBe("summa");
  });
});
