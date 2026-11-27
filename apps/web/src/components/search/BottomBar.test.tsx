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

  it("draws the top edge's rule between pills, selector and search box", () => {
    const { container } = renderBar(["bible"]);
    const bar = container.firstElementChild as HTMLElement;
    const rules = [...bar.children].filter((child) => child.getAttribute("aria-hidden") === "true");

    expect(rules).toHaveLength(2);
    for (const element of [bar, ...rules]) {
      for (const token of RULE) expect(element.classList).toContain(token);
    }
    // The inner rules bleed through the bar's px-4 to span its width, as its top edge does.
    for (const rule of rules) expect(rule.classList).toContain("-mx-4");

    const [first, second] = rules;
    const selectorRow = screen.getByRole("group", { name: "Results per source" }).closest(".py-3");
    expect(first.nextElementSibling).toBe(selectorRow);
    expect(selectorRow?.nextElementSibling).toBe(second);
  });

  it("centres the selector alone, with its label and save notice out of the flow", () => {
    renderBar(["bible"], "saved");
    const group = screen.getByRole("group", { name: "Results per source" });
    const row = group.closest(".py-3") as HTMLElement;
    expect(row.className).toContain("justify-center");

    const label = screen.getByText("Per source:");
    expect(label.className).toContain("absolute");
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("Default saved");
    expect(status.className).toContain("absolute");
    // Only the selector takes up room in the row, so it is what gets centred.
    expect([...row.children].filter((child) => !child.className.includes("absolute"))).toHaveLength(1);
    expect(screen.getByRole("button", { name: "10 passages per source" })).toBeTruthy();
  });
});
