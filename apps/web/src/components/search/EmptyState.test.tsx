// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ guestGate: null as null | { requestSignup: ReturnType<typeof vi.fn> } }));

vi.mock("@/lib/analytics", () => ({ trackSuggestedQueryClicked: vi.fn() }));

vi.mock("next/link", () => ({
  default: ({ children, href, prefetch, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { prefetch?: boolean | null }) => (
    <a href={String(href)} data-prefetch={prefetch === undefined ? "default" : String(prefetch)} {...props}>{children}</a>
  ),
}));

vi.mock("@/components/layout/guestGate", () => ({
  useGuestGate: () => state.guestGate,
}));

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
    state.guestGate = null;
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

  it("asks a guest to sign up instead of opening the Library", async () => {
    const requestSignup = vi.fn();
    state.guestGate = { requestSignup };
    await renderEmptyState();

    const link = screen.getByRole("link", { name: "Browse the Library" });
    expect(link.dataset.prefetch).toBe("false");
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    link.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(requestSignup).toHaveBeenCalledWith("library");
  });

  it("links a signed-in user to the Library", async () => {
    await renderEmptyState();

    const link = screen.getByRole("link", { name: "Browse the Library" });
    expect(link.getAttribute("href")).toBe("/sources");
    expect(link.dataset.prefetch).toBe("default");
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    link.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
  });
});
