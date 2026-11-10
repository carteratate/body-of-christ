import { describe, expect, it } from "vitest";
import {
  movedLine,
  parsePassageLifecycle,
  parseRedirect,
  parseTombstone,
  readElsewhere,
  removalExplainer,
  removalHeading,
} from "./corpus-lifecycle";

const TOMBSTONE = {
  entity: "passage",
  rule: "G",
  reason_code: "note-split-off",
  public_reason: "This card was a footnote to the document's text, not the text itself.",
  church_act: null,
  read_elsewhere_url: null,
  retired_at: "2026-12-01T00:00:00Z",
  title: "Pastores Gregis",
  author: "Pope John Paul II",
  reference: "Pastores Gregis, §39",
};

describe("removal wording", () => {
  it("says removed, or not available for a text that is only held back", () => {
    expect(removalHeading({ reason_code: "rule-a" })).toBe("Removed from TheoCorpus");
    expect(removalHeading({ reason_code: "awaiting-permission" })).toBe("Not available on TheoCorpus");
    expect(removalHeading({ reason_code: "translation-in-preparation" })).toBe("Not available on TheoCorpus");
    expect(removalExplainer({ reason_code: "debris" })).toEqual({ href: "/about", label: "Why was this removed?" });
    expect(removalExplainer({ reason_code: "awaiting-permission" }, true))
      .toEqual({ href: "/guest/about", label: "Why isn't this available?" });
  });

  it("names the site a held text can still be read at", () => {
    expect(readElsewhere({ read_elsewhere_url: "https://www.papalencyclicals.net/greg16/g16mirar.htm" }))
      .toEqual({ href: "https://www.papalencyclicals.net/greg16/g16mirar.htm", label: "Read it at papalencyclicals.net" });
    expect(readElsewhere({ read_elsewhere_url: null })).toBeNull();
    expect(readElsewhere({ read_elsewhere_url: "javascript:alert(1)" })).toBeNull();
  });

  it("describes each kind of move", () => {
    expect(movedLine("renumbered")).toBe("This passage was renumbered in a corpus update.");
    expect(movedLine(undefined)).toBe("This passage was renumbered in a corpus update.");
    expect(movedLine("moved")).toMatch(/moved/);
    expect(movedLine("split")).toMatch(/divided/);
    expect(movedLine("merged")).toMatch(/joined/);
  });
});

describe("parsing", () => {
  it("reads a tombstone and refuses one without its sentence", () => {
    expect(parseTombstone(TOMBSTONE)).toMatchObject({ entity: "passage", reason_code: "note-split-off", title: "Pastores Gregis" });
    expect(parseTombstone({ ...TOMBSTONE, public_reason: "" })).toBeNull();
    expect(parseTombstone(null)).toBeNull();
  });

  it("reads a redirect and refuses one without a document", () => {
    expect(parseRedirect({ kind: "renumbered", document_id: "d", anchor: "a", chunk_id: "c" }))
      .toEqual({ kind: "renumbered", document_id: "d", anchor: "a", chunk_id: "c", chapter_key: null });
    expect(parseRedirect({ kind: "moved" })).toBeNull();
  });

  it("leaves a result without lifecycle fields unchanged", () => {
    expect(parsePassageLifecycle({ chunk_id: "x" })).toEqual({});
  });

  it("treats a removal or move it cannot explain as current", () => {
    expect(parsePassageLifecycle({ status: "removed", tombstone: null }).status).toBe("current");
    expect(parsePassageLifecycle({ status: "moved", redirect: null }).status).toBe("current");
    expect(parsePassageLifecycle({ status: "removed", tombstone: TOMBSTONE }).status).toBe("removed");
  });
});
