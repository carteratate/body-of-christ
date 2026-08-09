// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResultFilterBar } from "./ResultFilterBar";

afterEach(cleanup);

describe("ResultFilterBar", () => {
  it("matches the compact scale of the pre-query source toggles", () => {
    const onToggleVisible = vi.fn();
    render(
      <ResultFilterBar
        submittedCollections={["bible", "catechism"]}
        visibleCollections={["bible", "catechism"]}
        onToggleVisible={onToggleVisible}
      />,
    );

    const bible = screen.getByRole("button", { name: "Bible" });
    expect(bible.className).toContain("px-3");
    expect(bible.className).toContain("py-1");
    expect(bible.className).toContain("text-xs");
    fireEvent.click(bible);
    expect(onToggleVisible).toHaveBeenCalledWith("bible");
  });
});
