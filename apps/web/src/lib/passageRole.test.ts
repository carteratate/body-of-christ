import { describe, expect, it } from "vitest";

import { displayRole } from "./passageRole";

describe("displayRole", () => {
  it("names a Summa objection, which reads as a flat assertion without it", () => {
    // Ingest moves "Objection N" out of `content` into `unit_label`, so the passage
    // itself gives the reader nothing: "It would seem that fear causes involuntariness
    // simply..." attributed to Aquinas, cited to the Summa.
    expect(displayRole("summa", "Objection 4", "ST II-II, Q. 110, Art. 3")).toBe("Objection 4");
    expect(displayRole("summa", "Reply to Objection 4", "ST II-II, Q. 110, Art. 3"))
      .toBe("Reply to Objection 4");
  });

  it("stays silent for collections whose label is a locator, not an argument role", () => {
    // "Can. 1055 §1" names where a passage sits, not whose position it states. Printing
    // it beside a citation that already locates the passage is noise.
    expect(displayRole("canon-law", "Can. 1055 §1", "Code of Canon Law")).toBeNull();
    expect(displayRole("bible", "1", "John 1:1")).toBeNull();
    expect(displayRole("catechism", "§17", "CCC 17")).toBeNull();
    expect(displayRole("church-fathers", "Chapter 3", "Confessions III")).toBeNull();
  });

  it("stays silent when there is no role at all", () => {
    expect(displayRole("summa", null, "ST I, Q. 1")).toBeNull();
    expect(displayRole("summa", undefined, "ST I, Q. 1")).toBeNull();
    expect(displayRole("summa", "   ", "ST I, Q. 1")).toBeNull();
  });

  it("does not repeat a role the citation already carries", () => {
    // Inert against today's corpus — 0 of 26,748 labelled Summa chunks have their
    // unit_label inside their reference — so this pins the guard's behaviour rather
    // than a case that occurs.
    expect(displayRole("summa", "Objection 4", "ST II-II, Q. 110, Art. 3, Objection 4"))
      .toBeNull();
  });

  it("handles a missing citation without suppressing the role", () => {
    expect(displayRole("summa", "Objection 4", null)).toBe("Objection 4");
  });
});
