// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchBar } from "./SearchBar";

afterEach(cleanup);

function renderBar(loading: boolean) {
  return render(
    <SearchBar value="grace" onChange={vi.fn()} onSubmit={vi.fn()} loading={loading} disabled={false} />,
  );
}

describe("SearchBar submit button", () => {
  it("shows the Search label when idle", () => {
    renderBar(false);
    const button = screen.getByRole("button", { name: "Search" });
    expect(button.getAttribute("aria-busy")).toBeNull();
    expect(button.textContent).not.toContain("Searching");
  });

  it("keeps the Search label in place, hidden, while loading so the button keeps its width", () => {
    renderBar(true);
    const button = screen.getByRole("button", { name: "Searching…" });
    const label = [...button.querySelectorAll("span")].find((span) => span.textContent === "Search");

    expect(label).toBeDefined();
    expect(label?.className).toContain("invisible");
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
