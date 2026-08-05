// @vitest-environment jsdom

import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistorySearchRow } from "./Sidebar";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={String(href)} {...props}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/search",
}));

vi.mock("./AppShell", () => ({
  useAppContext: vi.fn(),
}));

vi.mock("./guestGate", () => ({
  useGuestGate: () => null,
}));

function RowHarness({ onDelete = vi.fn() }: { onDelete?: () => void }) {
  const [revealed, setRevealed] = useState(false);
  return (
    <HistorySearchRow
      id="search-1"
      query="What is grace?"
      href="/search?restore=search-1"
      active={false}
      revealed={revealed}
      onNavigate={vi.fn()}
      onReveal={() => setRevealed(true)}
      onClose={() => setRevealed(false)}
      onDelete={onDelete}
    />
  );
}

afterEach(cleanup);

describe("HistorySearchRow", () => {
  it("requires a reveal click before desktop deletion", async () => {
    const onDelete = vi.fn();
    render(<RowHarness onDelete={onDelete} />);

    const reveal = screen.getByRole("button", {
      name: "Show delete option for What is grace?",
    });
    await userEvent.click(reveal);

    expect(onDelete).not.toHaveBeenCalled();
    const deleteButton = screen.getByRole("button", { name: "Delete search: What is grace?" });
    expect(deleteButton.getAttribute("aria-hidden")).toBe("false");
    expect(deleteButton.tabIndex).toBe(0);
    expect(document.activeElement).toBe(reveal);
    expect(reveal.tabIndex).toBe(-1);

    await userEvent.click(deleteButton);
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("rejects a pointer click on Delete unless Delete received a fresh pointer-down", async () => {
    const onDelete = vi.fn();
    render(<RowHarness onDelete={onDelete} />);

    await userEvent.click(
      screen.getByRole("button", { name: "Show delete option for What is grace?" }),
    );
    const deleteButton = screen.getByRole("button", { name: "Delete search: What is grace?" });

    // Guards against the reveal click landing on the panel after the row moves.
    fireEvent.click(deleteButton, { detail: 1 });
    expect(onDelete).not.toHaveBeenCalled();

    fireEvent.pointerDown(deleteButton, { pointerType: "mouse" });
    fireEvent.click(deleteButton, { detail: 1 });
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("keeps an assistive reveal action available on no-hover devices", () => {
    render(<RowHarness />);

    const reveal = screen.getByRole("button", {
      name: "Show delete option for What is grace?",
    });
    expect(reveal.className).toContain("[@media(hover:none)]:sr-only");
    expect(reveal.className).not.toContain("[@media(hover:none)]:hidden");
  });

  it("does not finish a swipe when the browser cancels the pointer", () => {
    render(<RowHarness />);
    const link = screen.getByRole("link", { name: "What is grace?" });
    const foreground = link.parentElement as HTMLDivElement;

    fireEvent.pointerDown(foreground, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 180,
      clientY: 20,
    });
    fireEvent.pointerMove(foreground, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 100,
      clientY: 22,
    });
    fireEvent.pointerCancel(foreground, { pointerId: 1, pointerType: "touch" });

    expect(
      document
        .querySelector('button[aria-label="Delete search: What is grace?"]')
        ?.getAttribute("aria-hidden"),
    ).toBe("true");
    expect(foreground.style.transform).toBe("translateX(0px)");
  });

  it("reveals the delete action after a left touch swipe", () => {
    render(<RowHarness />);
    const link = screen.getByRole("link", { name: "What is grace?" });
    const foreground = link.parentElement as HTMLDivElement;

    fireEvent.pointerDown(foreground, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 180,
      clientY: 20,
    });
    fireEvent.pointerMove(foreground, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 100,
      clientY: 22,
    });
    fireEvent.pointerUp(foreground, {
      pointerId: 1,
      pointerType: "touch",
      clientX: 100,
      clientY: 22,
    });

    const deleteButton = screen.getByRole("button", { name: "Delete search: What is grace?" });
    expect(deleteButton.getAttribute("aria-hidden")).toBe("false");
  });

  it("uses right click to reveal rather than immediately delete", () => {
    const onDelete = vi.fn();
    render(<RowHarness onDelete={onDelete} />);

    fireEvent.contextMenu(screen.getByRole("link", { name: "What is grace?" }).closest("[data-history-row]")!);

    expect(onDelete).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Delete search: What is grace?" }).getAttribute(
        "aria-hidden",
      ),
    ).toBe("false");
  });

  it("closes with Escape and restores focus to the reveal control", async () => {
    render(<RowHarness />);
    const reveal = screen.getByRole("button", {
      name: "Show delete option for What is grace?",
    });
    fireEvent.click(reveal, { detail: 0 });
    const deleteButton = screen.getByRole("button", { name: "Delete search: What is grace?" });
    await waitFor(() => expect(document.activeElement).toBe(deleteButton));

    fireEvent.keyDown(
      screen.getByRole("link", { name: "What is grace?" }).closest("[data-history-row]")!,
      { key: "Escape" },
    );

    const hiddenDelete = document.querySelector(
      'button[aria-label="Delete search: What is grace?"]',
    );
    expect(hiddenDelete?.getAttribute("aria-hidden")).toBe("true");
    await waitFor(() => expect(document.activeElement).toBe(reveal));
    expect(reveal.tabIndex).toBe(0);
  });
});
