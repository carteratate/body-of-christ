// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IntentLink, NavPendingBar } from "./NavPending";
import { linkStatus, navigations } from "@/test/next-link-mock";

const router = vi.hoisted(() => ({ prefetch: vi.fn(), push: vi.fn() }));
vi.mock("next/link", () => import("@/test/next-link-mock"));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  router.prefetch.mockReset();
  navigations.length = 0;
  linkStatus.pending = false;
});

describe("IntentLink", () => {
  it("never prefetches on sight or on press", () => {
    render(<IntentLink href="/reader/doc-a?from=search">Open</IntentLink>);
    const link = screen.getByRole("link", { name: "Open" });
    expect(link.dataset.prefetch).toBe("false");
    fireEvent.pointerDown(link, { pointerType: "mouse" });
    fireEvent.pointerDown(link, { pointerType: "touch" });
    expect(router.prefetch).not.toHaveBeenCalled();
  });

  it("prefetches once the mouse rests on it, and not when it only passes over", () => {
    vi.useFakeTimers();
    render(<IntentLink href="/reader/doc-a?from=search">Open</IntentLink>);
    const link = screen.getByRole("link", { name: "Open" });

    fireEvent.pointerEnter(link, { pointerType: "mouse" });
    vi.advanceTimersByTime(149);
    fireEvent.pointerLeave(link, { pointerType: "mouse" });
    vi.advanceTimersByTime(1_000);
    expect(router.prefetch).not.toHaveBeenCalled();

    fireEvent.pointerEnter(link, { pointerType: "mouse" });
    vi.advanceTimersByTime(150);
    expect(router.prefetch).toHaveBeenCalledExactlyOnceWith("/reader/doc-a?from=search");

    // Touch has no hover.
    router.prefetch.mockClear();
    fireEvent.pointerEnter(link, { pointerType: "touch" });
    vi.advanceTimersByTime(1_000);
    expect(router.prefetch).not.toHaveBeenCalled();
  });

  it("prefetches after keyboard focus stays, not after scripted focus", () => {
    vi.useFakeTimers();
    render(<IntentLink href="/feedback">Report</IntentLink>);
    const link = screen.getByRole("link", { name: "Report" });
    const matches = vi.spyOn(link, "matches");

    matches.mockReturnValue(false);
    fireEvent.focus(link);
    vi.advanceTimersByTime(1_000);
    expect(router.prefetch).not.toHaveBeenCalled();

    matches.mockReturnValue(true);
    fireEvent.focus(link);
    vi.advanceTimersByTime(150);
    expect(router.prefetch).toHaveBeenCalledExactlyOnceWith("/feedback");
  });

  it("runs onClick for every click and onNavigate only for a same-tab one", () => {
    const onClick = vi.fn();
    const onNavigate = vi.fn();
    render(<IntentLink href="/feedback" onClick={onClick} onNavigate={onNavigate}>Report</IntentLink>);
    const link = screen.getByRole("link", { name: "Report" });

    link.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, metaKey: true }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(onNavigate).not.toHaveBeenCalled();

    fireEvent.click(link);
    expect(onClick).toHaveBeenCalledTimes(2);
    expect(onNavigate).toHaveBeenCalledTimes(1);
    expect(navigations).toEqual(["/feedback"]);
  });

  it("shows the pending line while its navigation is in flight", () => {
    const { rerender } = render(<IntentLink href="/feedback">Report</IntentLink>);
    const bar = screen.getByRole("link", { name: "Report" }).querySelector(".nav-pending")!;
    expect(bar.getAttribute("aria-hidden")).toBe("true");
    expect(bar.getAttribute("data-pending")).toBeNull();
    linkStatus.pending = true;
    rerender(<IntentLink href="/feedback">Report</IntentLink>);
    expect(bar.getAttribute("data-pending")).toBe("true");
  });
});

describe("NavPendingBar", () => {
  it("is always rendered, so turning it on never shifts layout", () => {
    const { container, rerender } = render(<NavPendingBar pending={false} />);
    const bar = container.querySelector(".nav-pending")!;
    rerender(<NavPendingBar pending />);
    expect(container.querySelector(".nav-pending")).toBe(bar);
    expect(bar.getAttribute("data-pending")).toBe("true");
  });
});
