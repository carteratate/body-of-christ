import { describe, expect, it } from "vitest";

import { copiedCredit, parseOverviewNotes, parsePassageCard, splitAtLink } from "./card-notes";

describe("parsePassageCard", () => {
  it("is null for a response from before 4.4", () => {
    expect(parsePassageCard(undefined)).toBeNull();
    expect(parsePassageCard(null)).toBeNull();
    expect(parsePassageCard("card")).toBeNull();
    expect(parsePassageCard([])).toBeNull();
  });

  it("keeps an empty card, whose presence selects the new rendering", () => {
    expect(parsePassageCard({})).toEqual({ cautions: [], record: [], notice: null });
  });

  it("drops a malformed entry, never the card", () => {
    expect(parsePassageCard({
      cautions: [
        { kind: "doubt", text: "Unknown kind." },
        { kind: "wording", text: "  " },
        "text",
        { kind: "incomplete", text: "Kept.", link: { label: "Here", href: "javascript:alert(1)" } },
        { kind: "authority", text: "Superseded.", link: { label: "Read the current text", document_id: "d2" } },
      ],
      record: ["One", 2, " ", "Two"],
      notice: 7,
    })).toEqual({
      cautions: [
        { kind: "incomplete", text: "Kept.", link: null },
        { kind: "authority", text: "Superseded.", link: { label: "Read the current text", href: null, document_id: "d2" } },
      ],
      record: ["One", "Two"],
      notice: null,
    });
  });
});

describe("parseOverviewNotes", () => {
  it("is null for a document from before 4.4 and keeps record notes without a kind", () => {
    expect(parseOverviewNotes(undefined)).toBeNull();
    expect(parseOverviewNotes(null)).toBeNull();
    expect(parseOverviewNotes([{ kind: "incomplete", text: "Six canons are not shown." },
      { kind: null, text: "Preserved in Eusebius." }, { text: "" }]))
      .toEqual([{ kind: "incomplete", text: "Six canons are not shown." },
        { kind: null, text: "Preserved in Eusebius." }]);
  });
});

describe("copiedCredit", () => {
  it("is the card's notice with a card, today's credit without one", () => {
    expect(copiedCredit({ cautions: [], record: [], notice: null }, "Sourced via CCEL.org")).toBeNull();
    expect(copiedCredit({ cautions: [], record: [], notice: "© LEV" }, "© LEV")).toBe("© LEV");
    expect(copiedCredit(null, "Sourced via CCEL.org")).toBe("Sourced via CCEL.org");
  });
});

describe("splitAtLink", () => {
  it("links the label in place, or appends a label the text does not hold", () => {
    expect(splitAtLink({ kind: "wording", text: "Unofficial. The Latin text is official.",
      link: { label: "The Latin text is official." } }))
      .toEqual({ before: "Unofficial. ", label: "The Latin text is official.", after: "" });
    expect(splitAtLink({ kind: "authority", text: "Superseded.", link: { label: "Read the current text" } }))
      .toEqual({ before: "Superseded. ", label: "Read the current text", after: "" });
    expect(splitAtLink({ kind: "authority", text: "Superseded." }))
      .toEqual({ before: "Superseded.", label: null, after: "" });
  });
});
