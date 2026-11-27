// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomBar } from "./BottomBar";

function renderBar(activeCollections: string[], preferenceSaveStatus: "saved" | null = null) {
  return render(
    <BottomBar
      activeCollections={activeCollections}
      onToggleCollection={vi.fn()}
      quota={3}
      onQuotaChange={vi.fn()}
      preferenceSaveStatus={preferenceSaveStatus}
      searchValue=""
      onSearchChange={vi.fn()}
      onSearch={vi.fn()}
      loading={false}
      isSearchActive={false}
      submittedCollections={[]}
      visibleCollections={[]}
      onToggleVisible={vi.fn()}
    />,
  );
}

const RULE = ["border-t", "border-brand-surface"];

describe("BottomBar layout", () => {
  afterEach(cleanup);

  it("has no Sources label, and centres the pills on phones", () => {
    renderBar(["bible"]);
    expect(screen.queryByText(/sources:/i)).toBeNull();
    const pills = screen.getByRole("button", { name: "Bible" }).parentElement!;
    expect(pills.className).toContain("max-md:justify-center");
  });

  it("on phones only, draws the top edge's rule between pills, selector and search box", () => {
    const { container } = renderBar(["bible"]);
    const bar = container.firstElementChild as HTMLElement;
    const rules = [...bar.querySelectorAll('[aria-hidden="true"]')]
      .filter((element) => element.classList.contains("-mx-4"));

    expect(rules).toHaveLength(2);
    for (const element of [bar, ...rules]) {
      for (const token of RULE) expect(element.classList).toContain(token);
    }
    // Laptops keep today's single row: the rules exist only below the md breakpoint.
    for (const rule of rules) expect(rule.classList).toContain("md:hidden");

    const [first, second] = rules;
    const selectorColumn = screen.getByRole("group", { name: "Results per source" }).closest(".max-md\\:py-3");
    expect(first.nextElementSibling).toBe(selectorColumn);
    expect(selectorColumn?.nextElementSibling).toBe(second);
  });

  it("on phones, centres the selector alone, with its label and save notice out of the flow", () => {
    renderBar(["bible"], "saved");
    const group = screen.getByRole("group", { name: "Results per source" });
    const column = group.closest(".max-md\\:py-3") as HTMLElement;
    // Laptops keep the selector at the row's end; phones centre it.
    expect(column.className).toContain("items-end");
    expect(column.className).toContain("max-md:items-center");

    expect(screen.getByText("Per source:").className).toContain("max-md:absolute");
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("Default saved");
    expect(status.className).toContain("max-md:absolute");
    expect(screen.getByRole("button", { name: "10 passages per source" })).toBeTruthy();
  });
});
