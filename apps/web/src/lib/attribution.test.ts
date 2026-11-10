import { describe, expect, it } from "vitest";
import {
  certaintyTag,
  factNotes,
  formatAttribution,
  formatDate,
  formatTranslation,
  parseFacts,
  siteName,
  sourceCreditOf,
} from "./attribution";

describe("formatAttribution", () => {
  it("keeps the registry's author for a pseudonymous or anonymous work", () => {
    expect(formatAttribution("Pseudo-Justin", { certainty: "pseudonymous" })).toBe("Pseudo-Justin");
    expect(formatAttribution("Anonymous", { certainty: "anonymous" })).toBe("Anonymous");
    expect(formatAttribution(null, { certainty: "anonymous" })).toBe("Anonymous");
  });

  it("says when authorship is disputed, unless a tag shows it beside the line", () => {
    expect(formatAttribution("Justin Martyr", { certainty: "disputed" })).toBe("Justin Martyr (authorship disputed)");
    expect(formatAttribution("Justin Martyr", { certainty: "disputed" }, null, { certainty: false })).toBe("Justin Martyr");
  });

  it("credits a quoted author, and where the quotation stands", () => {
    expect(formatAttribution("Thomas Aquinas", null, "Chrysostom", { work: "Catena Aurea" }))
      .toBe("Chrysostom, quoted in Thomas Aquinas's Catena Aurea");
    expect(formatAttribution("Aquinas", null, "Chrysostom")).toBe("Chrysostom, quoted by Aquinas");
    expect(formatAttribution(null, null, "Chrysostom")).toBe("Chrysostom");
    expect(formatAttribution("Eusebius", null, "Papias", { work: "Church History" }))
      .toBe("Papias, quoted in Eusebius's Church History");
  });

  it("is today's author without facts", () => {
    expect(formatAttribution("Augustine")).toBe("Augustine");
    expect(formatAttribution(null)).toBeNull();
    expect(formatAttribution("  ")).toBeNull();
  });
});

describe("formatDate", () => {
  it("prefers the display date, then the year", () => {
    expect(formatDate({ date_display: "397–400", year: 397 })).toBe("397–400");
    expect(formatDate({ year: 397 })).toBe("397");
    expect(formatDate(null, 1891)).toBe("1891");
    expect(formatDate({}, 0)).toBeNull();
    expect(formatDate(undefined)).toBeNull();
  });
});

describe("formatTranslation", () => {
  it("names a known code and keeps any other text", () => {
    expect(formatTranslation("WEB-C")).toBe("World English Bible, Catholic Edition");
    expect(formatTranslation("Translated by William Harman van Allen (1909)"))
      .toBe("Translated by William Harman van Allen (1909)");
    expect(formatTranslation("")).toBeNull();
    expect(formatTranslation(null)).toBeNull();
  });
});

describe("certaintyTag", () => {
  it("tags everything but a genuine attribution", () => {
    expect(certaintyTag("genuine")).toBeNull();
    expect(certaintyTag(null)).toBeNull();
    expect(certaintyTag("disputed")).toBe("disputed");
    expect(certaintyTag("pseudonymous")).toBe("pseudonymous");
    expect(certaintyTag("anonymous")).toBe("anonymous");
    expect(certaintyTag("other")).toBeNull();
  });
});

describe("factNotes", () => {
  it("lists the attribution note, the document's notes and the passage's, without repeats", () => {
    expect(factNotes({ attribution_note: "Not by Justin Martyr.", notes: "A note." }, "Passage note."))
      .toEqual(["Not by Justin Martyr.", "A note.", "Passage note."]);
    expect(factNotes({ notes: "Same." }, "Same.")).toEqual(["Same."]);
    expect(factNotes(null)).toEqual([]);
  });
});

describe("sourceCreditOf", () => {
  it("takes the facts' credit, else the excerpt-only notice", () => {
    expect(sourceCreditOf({ source_credit: "Sourced via CCEL.org" }, null)).toBe("Sourced via CCEL.org");
    expect(sourceCreditOf(null, "USCCB notice")).toBe("USCCB notice");
    expect(sourceCreditOf({ source_credit: " " }, null)).toBeNull();
  });
});

describe("siteName", () => {
  it("names the site without www", () => {
    expect(siteName("https://www.papalencyclicals.net/greg16/g16mirar.htm")).toBe("papalencyclicals.net");
    expect(siteName("https://www.vatican.va/x.html")).toBe("vatican.va");
    expect(siteName("javascript:alert(1)")).toBeNull();
    expect(siteName("not a url")).toBeNull();
  });
});

describe("parseFacts", () => {
  it("keeps well-typed fields and drops the rest", () => {
    expect(parseFacts({ year: 397, certainty: "disputed", notes: "n", translation: 3, certainty_x: 1 }))
      .toEqual({ year: 397, certainty: "disputed", notes: "n" });
    expect(parseFacts({ certainty: "maybe" })).toEqual({});
    expect(parseFacts("facts")).toBeNull();
    expect(parseFacts(null)).toBeNull();
  });
});
