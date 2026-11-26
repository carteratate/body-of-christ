// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchBar, searchPlaceholder } from "./SearchBar";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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
  it("uses one-line hints on narrow screens and the full wording on wider ones", () => {
    expect(searchPlaceholder(false, true)).toBe("What's on your mind?");
    expect(searchPlaceholder(true, true)).toBe("Select a source to search.");
    expect(searchPlaceholder(false, false)).toBe("A question, a thought, a doubt: what's on your mind?");
    expect(searchPlaceholder(true, false)).toBe("Select at least one source to search.");
  });

  function stubViewport(narrow: boolean) {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: narrow && query === "(max-width: 767px)",
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
  }

  it("shows the short hints on a phone, keeping the button's full disabled title", () => {
    stubViewport(true);
    render(<SearchBar value="" onChange={vi.fn()} onSubmit={vi.fn()} loading={false} disabled />);

    expect(screen.getByRole("textbox").getAttribute("placeholder")).toBe("Select a source to search.");
    expect(screen.getByRole("button").getAttribute("title")).toBe("Select at least one source to search.");
  });

  it("shows the full hint on a wider screen", () => {
    stubViewport(false);
    render(<SearchBar value="" onChange={vi.fn()} onSubmit={vi.fn()} loading={false} disabled={false} />);

    expect(screen.getByRole("textbox").getAttribute("placeholder")).toBe(
      "A question, a thought, a doubt: what's on your mind?",
    );
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
