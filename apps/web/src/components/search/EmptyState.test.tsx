// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/analytics", () => ({ trackSuggestedQueryClicked: vi.fn() }));

const FIRST_FOUR = [
  "Is it ever right to lie? Does intention matter, or is deception always wrong?",
  "Why does God allow suffering?",
  "If God knows everything that will happen, how can our choices be free?",
  "Is it a sin to be wealthy? What is the proper relationship between a Christian and money?",
];

// The client pick is cached per module, so each test loads a fresh copy.
async function renderEmptyState(onSelectQuery = vi.fn()) {
  vi.resetModules();
  const { EmptyState } = await import("./EmptyState");
  render(<EmptyState onSelectQuery={onSelectQuery} />);
  return screen.getAllByRole("button").map((button) => button.textContent ?? "");
}

describe("EmptyState", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows four distinct suggestions", async () => {
    const chips = await renderEmptyState();

    expect(chips).toHaveLength(4);
    expect(new Set(chips).size).toBe(4);
  });

  it("can show suggestions beyond the first four in the list", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0);

    const chips = await renderEmptyState();

    expect(chips.some((chip) => !FIRST_FOUR.includes(chip))).toBe(true);
  });

  it("forwards the clicked suggestion", async () => {
    const onSelectQuery = vi.fn();
    const chips = await renderEmptyState(onSelectQuery);

    await userEvent.click(screen.getByRole("button", { name: chips[0] }));

    expect(onSelectQuery).toHaveBeenCalledWith(chips[0]);
  });
});
