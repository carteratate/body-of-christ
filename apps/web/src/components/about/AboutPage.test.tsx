// @vitest-environment jsdom

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AboutPage } from "./AboutPage";

afterEach(cleanup);

describe("AboutPage", () => {
  it("names no author or claim the corpus does not support", () => {
    const { container } = render(<AboutPage />);
    const text = container.textContent ?? "";
    for (const absent of [
      "Origen",
      "Chrysostom",
      "Bonaventure",
      "Hildegard",
      "Scotus",
      "counsels",
      "8th centuries",
      "canonists",
      "post-synodal",
    ]) {
      expect(text.toLowerCase()).not.toContain(absent.toLowerCase());
    }
  });

  it("names the authors the corpus holds", () => {
    const { container } = render(<AboutPage />);
    const text = container.textContent ?? "";
    for (const present of [
      "Irenaeus",
      "Bernard of Clairvaux",
      "Thomas à Kempis",
      "Boethius",
      "church councils",
    ]) {
      expect(text).toContain(present);
    }
  });

  it.each([false, true])("names the Catechism collection's three documents (guest: %s)", (isGuest) => {
    const { container } = render(<AboutPage isGuest={isGuest} />);
    const text = container.textContent ?? "";
    for (const present of [
      "Catechism of the Catholic Church (CCC)",
      "Compendium of the Catechism of the Catholic Church (2005)",
      "Catechism of the Council of Trent (1566)",
      "McHugh and Charles J. Callan's 1923 translation",
    ]) {
      expect(text).toContain(present);
    }
  });
});
