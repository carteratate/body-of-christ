// @vitest-environment jsdom

import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistorySearchRow } from "@/components/history";
import { Sidebar } from "./Sidebar";
import { useAppContext } from "./AppShell";

const navigationState = vi.hoisted(() => ({ pathname: "/search", params: "" }));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={String(href)} {...props}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => navigationState.pathname,
  useSearchParams: () => new URLSearchParams(navigationState.params),
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
      search={{
        id: "search-1",
        query: "What is grace?",
        filters: null,
        result_count: 4,
        created_at: "2026-08-04T12:00:00Z",
      }}
      active={false}
      revealed={revealed}
      onReveal={() => setRevealed(true)}
      onClose={() => setRevealed(false)}
      onDelete={onDelete}
    />
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  navigationState.pathname = "/search";
  navigationState.params = "";
});

function mockMatchMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

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

  it("keeps the reveal X visibly available on every device", () => {
    render(<RowHarness />);

    const reveal = screen.getByRole("button", {
      name: "Show delete option for What is grace?",
    });
    expect(reveal.className).toContain("opacity-100");
    expect(reveal.className).not.toContain("group-hover");
    expect(reveal.className).not.toContain("sr-only");
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

describe("Sidebar mobile accessibility", () => {
  it("uses Search History as the only history surface in the sidebar", async () => {
    mockMatchMedia(false);
    vi.mocked(useAppContext).mockReturnValue({
      newSearch: vi.fn(),
      token: "token",
    } as unknown as ReturnType<typeof useAppContext>);

    render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);

    expect(await screen.findByRole("link", { name: "Search History" })).toBeTruthy();
    expect(screen.queryByText("RECENT")).toBeNull();
    expect(document.getElementById("sidebar-recent-searches")).toBeNull();
  });

  it("keeps Search History active while a restored result is shown", async () => {
    mockMatchMedia(false);
    navigationState.params = "restore=11111111-1111-4111-8111-111111111111";
    vi.mocked(useAppContext).mockReturnValue({ newSearch: vi.fn(), token: "token" } as unknown as ReturnType<typeof useAppContext>);

    render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);

    expect((await screen.findByRole("link", { name: "Search History" })).className).toContain("text-brand-accent");
  });

  it("removes the closed offscreen drawer from keyboard and accessibility navigation", async () => {
    mockMatchMedia(true);
    vi.mocked(useAppContext).mockReturnValue({
      newSearch: vi.fn(),
      searches: [],
      pendingSearch: null,
      activeSearchId: null,
      token: "token",
      removeSearch: vi.fn(),
      restoreSearch: vi.fn(),
      refreshSearches: vi.fn(),
      invalidateSearchHistory: vi.fn(),
    } as unknown as ReturnType<typeof useAppContext>);

    const { rerender } = render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);
    await waitFor(() => expect(document.getElementById("mobile-nav-drawer")?.getAttribute("aria-hidden")).toBe("true"));
    const closed = document.getElementById("mobile-nav-drawer")!;
    expect(closed.hasAttribute("inert")).toBe(true);
    expect(closed.getAttribute("role")).toBeNull();

    rerender(<Sidebar isMobileOpen onCloseMobile={vi.fn()} />);
    await waitFor(() => expect(document.getElementById("mobile-nav-drawer")?.getAttribute("role")).toBe("dialog"));
    const open = document.getElementById("mobile-nav-drawer")!;
    expect(open.hasAttribute("inert")).toBe(false);
    expect(open.getAttribute("aria-hidden")).toBeNull();
  });
});
