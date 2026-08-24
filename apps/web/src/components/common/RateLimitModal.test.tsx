// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RateLimitModal } from "./RateLimitModal";

vi.mock("@/lib/analytics", () => ({ trackRateLimitHit: vi.fn() }));

describe("RateLimitModal", () => {
  beforeEach(() => vi.useFakeTimers());

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("counts down from the supplied per-minute delay", () => {
    render(<RateLimitModal limitType="per_minute" retryAfter={3} onDismiss={vi.fn()} />);

    expect(screen.getByText(/resets in 3 seconds/)).toBeTruthy();
    act(() => vi.advanceTimersByTime(1_000));
    expect(screen.getByText(/resets in 2 seconds/)).toBeTruthy();
    act(() => vi.advanceTimersByTime(1_000));
    expect(screen.getByText(/resets in 1 second\./)).toBeTruthy();
    act(() => vi.advanceTimersByTime(1_000));
    expect(screen.getByText(/resetting shortly/)).toBeTruthy();
  });

  it("uses a 60-second fallback and resets when remounted", () => {
    const view = render(<RateLimitModal limitType="per_minute" retryAfter={null} onDismiss={vi.fn()} />);
    expect(screen.getByText(/resets in 60 seconds/)).toBeTruthy();

    act(() => vi.advanceTimersByTime(2_000));
    expect(screen.getByText(/resets in 58 seconds/)).toBeTruthy();

    view.unmount();
    render(<RateLimitModal limitType="per_minute" retryAfter={null} onDismiss={vi.fn()} />);
    expect(screen.getByText(/resets in 60 seconds/)).toBeTruthy();
  });

  it("shows the daily policy and dismisses from the button or backdrop", () => {
    const onDismiss = vi.fn();
    render(<RateLimitModal limitType="daily" retryAfter={18} onDismiss={onDismiss} />);

    expect(screen.getByText(/daily limit of 30 searches/)).toBeTruthy();
    act(() => vi.advanceTimersByTime(5_000));
    expect(screen.getByText(/daily limit of 30 searches/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "OK" }));
    expect(onDismiss).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("dialog").parentElement!);
    expect(onDismiss).toHaveBeenCalledTimes(2);
  });
});
