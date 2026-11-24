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
      "church councils",
    ]) {
      expect(text).toContain(present);
    }
  });

  it("lists the Fathers without Boethius, who stays in the collection", () => {
    const { container } = render(<AboutPage />);
    expect(container.textContent).toContain(
      "Writings of the early Church Fathers from roughly the 1st through 6th centuries, including Clement of Rome, Ignatius of Antioch, Justin Martyr, Irenaeus, Cyprian, Athanasius and Augustine.",
    );
    expect(container.textContent).not.toContain("Boethius");
  });
});
