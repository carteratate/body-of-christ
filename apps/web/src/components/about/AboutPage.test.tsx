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
});
