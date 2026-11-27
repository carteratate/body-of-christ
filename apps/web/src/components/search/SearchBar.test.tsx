// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchBar } from "./SearchBar";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

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

describe("SearchBar placeholder", () => {
  it("shows the full hints, and the button keeps its full disabled title", () => {
    const { rerender } = render(
      <SearchBar value="" onChange={vi.fn()} onSubmit={vi.fn()} loading={false} disabled={false} />,
    );
    expect(screen.getByRole("textbox").getAttribute("placeholder")).toBe(
      "A question, a thought, a doubt: what's on your mind?",
    );

    rerender(<SearchBar value="" onChange={vi.fn()} onSubmit={vi.fn()} loading={false} disabled />);
    expect(screen.getByRole("textbox").getAttribute("placeholder")).toBe("Select at least one source to search.");
    expect(screen.getByRole("button").getAttribute("title")).toBe("Select at least one source to search.");
  });

  it("sizes an empty box to its hint, since Safari leaves a wrapped placeholder out of scrollHeight", () => {
    // jsdom has no layout: report two lines for any text, one line for an empty value.
    vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockImplementation(function (
      this: HTMLTextAreaElement,
    ) {
      return this.value === "" ? 42 : 64;
    });
    render(<SearchBar value="" onChange={vi.fn()} onSubmit={vi.fn()} loading={false} disabled={false} />);

    const box = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(box.style.height).toBe("64px");
    expect(box.value).toBe("");
    expect(document.querySelectorAll("textarea")).toHaveLength(1);
  });
});

describe("SearchBar server render", () => {
  it("sends no hint before the browser reports its width", async () => {
    const { renderToString } = await import("react-dom/server");
    const html = renderToString(
      <SearchBar value="" onChange={vi.fn()} onSubmit={vi.fn()} loading={false} disabled={false} />,
    );
    expect(html).toContain('placeholder=""');
  });
});
