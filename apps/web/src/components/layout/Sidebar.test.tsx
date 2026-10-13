// @vitest-environment jsdom

import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistorySearchRow } from "@/components/history";
import { Sidebar } from "./Sidebar";
import { useAppContext } from "./AppShell";
import { GUEST_SEARCH_LIMIT } from "@/lib/trial";

const navigationState = vi.hoisted(() => ({ pathname: "/search", params: "", push: vi.fn(), prefetch: vi.fn(), guestGate: null as null | { requestSignup: ReturnType<typeof vi.fn>; searchCount: number } }));

vi.mock("next/link", () => ({
  default: ({ children, href, prefetch, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { prefetch?: boolean | null }) => (
    <a href={String(href)} data-prefetch={prefetch === undefined ? "default" : String(prefetch)} {...props}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: navigationState.push, prefetch: navigationState.prefetch }),
  usePathname: () => navigationState.pathname,
  useSearchParams: () => new URLSearchParams(navigationState.params),
}));

vi.mock("./AppShell", () => ({
  useAppContext: vi.fn(),
}));

vi.mock("./guestGate", () => ({
  useGuestGate: () => navigationState.guestGate,
}));

function RowHarness({
  onDelete = vi.fn(),
  showDate = false,
}: {
  onDelete?: () => void;
  showDate?: boolean;
}) {
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
      showDate={showDate}
      onReveal={() => setRevealed(true)}
      onClose={() => setRevealed(false)}
      onDelete={onDelete}
    />
  );
}

afterEach(() => {
  vi.useRealTimers();
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  navigationState.pathname = "/search";
  navigationState.params = "";
  navigationState.push.mockReset();
  navigationState.prefetch.mockReset();
  navigationState.guestGate = null;
});

function mockMatchMedia(matches: boolean) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

describe("HistorySearchRow", () => {
  it("prefetches its restore route once the pointer rests on it, not on sight", () => {
    vi.useFakeTimers();
    const onIntent = vi.fn();
    const props = {
      search: { id: "search-1", query: "What is grace?", filters: null, result_count: 4, created_at: "2026-08-04T12:00:00Z" },
      onIntent,
      onReveal: vi.fn(),
      onClose: vi.fn(),
      onDelete: vi.fn(),
    };
    const { rerender } = render(<HistorySearchRow {...props} revealed={false} />);
    const link = screen.getByRole("link", { name: "What is grace?" });
    expect(link.getAttribute("href")).toBe("/search?restore=search-1");
    expect(link.dataset.prefetch).toBe("false");
    vi.advanceTimersByTime(1_000);
    expect(navigationState.prefetch).not.toHaveBeenCalled();

    // Sweeping across the row warms nothing.
    fireEvent.pointerEnter(link, { pointerType: "mouse" });
    vi.advanceTimersByTime(100);
    fireEvent.pointerLeave(link, { pointerType: "mouse" });
    vi.advanceTimersByTime(1_000);
    expect(navigationState.prefetch).not.toHaveBeenCalled();

    // Resting on it does.
    fireEvent.pointerEnter(link, { pointerType: "mouse" });
    vi.advanceTimersByTime(150);
    expect(navigationState.prefetch).toHaveBeenCalledExactlyOnceWith("/search?restore=search-1");
    expect(onIntent).toHaveBeenCalledTimes(2);

    // Touch and a revealed (delete-exposed) row never prefetch.
    navigationState.prefetch.mockClear();
    fireEvent.pointerEnter(link, { pointerType: "touch" });
    fireEvent.pointerDown(link, { pointerType: "touch" });
    rerender(<HistorySearchRow {...props} revealed />);
    fireEvent.pointerEnter(link, { pointerType: "mouse" });
    vi.advanceTimersByTime(1_000);
    expect(navigationState.prefetch).not.toHaveBeenCalled();
  });

  it("shows the date only when requested", () => {
    vi.spyOn(Date.prototype, "toLocaleDateString").mockReturnValue("Aug 4, 2026");
    vi.spyOn(Date.prototype, "toLocaleTimeString").mockReturnValue("8:00 AM");

    const { rerender } = render(<RowHarness showDate />);

    expect(screen.getByText("4 results · Aug 4, 2026 · 8:00 AM")).toBeTruthy();

    rerender(<RowHarness />);

    expect(screen.getByText("4 results · 8:00 AM")).toBeTruthy();
    expect(screen.queryByText(/Aug 4, 2026/)).toBeNull();
  });

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
  it("lets guests open About and Feedback without showing the signup gate", async () => {
    mockMatchMedia(false);
    const requestSignup = vi.fn();
    navigationState.guestGate = { requestSignup, searchCount: 0 };
    vi.mocked(useAppContext).mockReturnValue({ newSearch: vi.fn(), token: null } as unknown as ReturnType<typeof useAppContext>);
    render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);

    const about = screen.getByRole("link", { name: "About" });
    const feedback = screen.getByRole("link", { name: "Feedback" });
    // The hrefs are the guest pages themselves, so the Link prefetches the page
    // the click opens and navigates without a router.push detour.
    expect(about.getAttribute("href")).toBe("/guest/about");
    expect(feedback.getAttribute("href")).toBe("/guest/feedback");
    expect(about.dataset.prefetch).toBe("default");
    expect(feedback.dataset.prefetch).toBe("default");

    const prevented: boolean[] = [];
    const record = (event: MouseEvent) => prevented.push(event.defaultPrevented);
    document.addEventListener("click", record);
    await userEvent.click(about);
    await userEvent.click(feedback);
    document.removeEventListener("click", record);

    expect(prevented).toEqual([false, false]);
    expect(navigationState.push).not.toHaveBeenCalled();
    expect(requestSignup).not.toHaveBeenCalled();
  });

  it("does not prefetch the links a guest cannot open, and gates them", async () => {
    mockMatchMedia(false);
    const requestSignup = vi.fn();
    navigationState.guestGate = { requestSignup, searchCount: 0 };
    vi.mocked(useAppContext).mockReturnValue({ newSearch: vi.fn(), token: null } as unknown as ReturnType<typeof useAppContext>);
    render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);

    const locked: [string, string][] = [
      ["Library", "library"],
      ["Saved Passages", "saved"],
      ["Search History", "history"],
      ["Source Guide", "feature"],
      ["Settings", "feature"],
    ];
    for (const [name, reason] of locked) {
      const link = screen.getByRole("link", { name });
      expect(link.dataset.prefetch, name).toBe("false");
      const event = new MouseEvent("click", { bubbles: true, cancelable: true });
      link.dispatchEvent(event);
      expect(event.defaultPrevented, name).toBe(true);
      expect(requestSignup).toHaveBeenLastCalledWith(reason);
    }
  });

  it("keeps default prefetch and the signed-in hrefs for signed-in users", async () => {
    mockMatchMedia(false);
    vi.mocked(useAppContext).mockReturnValue({ newSearch: vi.fn(), token: "token" } as unknown as ReturnType<typeof useAppContext>);
    render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);

    for (const [name, href] of [
      ["Library", "/sources"],
      ["Saved Passages", "/bookmarks"],
      ["Search History", "/history"],
      ["Source Guide", "/discover"],
      ["About", "/about"],
      ["Feedback", "/feedback"],
      ["Settings", "/settings"],
    ]) {
      const link = screen.getByRole("link", { name });
      expect(link.getAttribute("href"), name).toBe(href);
      expect(link.dataset.prefetch, name).toBe("default");
    }
  });

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

describe("Sidebar New Search", () => {
  it("prefetches /search up front and navigates there, resetting the search", async () => {
    mockMatchMedia(false);
    const newSearch = vi.fn();
    navigationState.pathname = "/sources";
    vi.mocked(useAppContext).mockReturnValue({ newSearch, token: "token" } as unknown as ReturnType<typeof useAppContext>);
    render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);

    expect(navigationState.prefetch).toHaveBeenCalledWith("/search");
    await userEvent.click(screen.getByRole("button", { name: "New Search" }));
    expect(navigationState.push).toHaveBeenCalledWith("/search");
    expect(newSearch).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "New Search" }).querySelector(".nav-pending")).toBeTruthy();
  });

  it("prefetches the guest search page for a guest under the limit, keeping preview", async () => {
    mockMatchMedia(false);
    navigationState.params = "preview=1";
    navigationState.guestGate = { requestSignup: vi.fn(), searchCount: 0 };
    vi.mocked(useAppContext).mockReturnValue({ newSearch: vi.fn(), token: null } as unknown as ReturnType<typeof useAppContext>);
    render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);

    expect(navigationState.prefetch).toHaveBeenCalledWith("/search/guest?preview=1");
    await userEvent.click(screen.getByRole("button", { name: "New Search" }));
    expect(navigationState.push).toHaveBeenCalledWith("/search/guest?preview=1");
  });

  it("gates a guest at the limit without prefetching or navigating", async () => {
    mockMatchMedia(false);
    const requestSignup = vi.fn();
    navigationState.guestGate = { requestSignup, searchCount: GUEST_SEARCH_LIMIT };
    vi.mocked(useAppContext).mockReturnValue({ newSearch: vi.fn(), token: null } as unknown as ReturnType<typeof useAppContext>);
    render(<Sidebar isMobileOpen={false} onCloseMobile={vi.fn()} />);

    const button = screen.getByRole("button", { name: "New Search" });
    fireEvent.pointerDown(button, { pointerType: "mouse" });
    await userEvent.click(button);
    expect(requestSignup).toHaveBeenCalledWith("limit");
    expect(navigationState.prefetch).not.toHaveBeenCalled();
    expect(navigationState.push).not.toHaveBeenCalled();
  });
});

