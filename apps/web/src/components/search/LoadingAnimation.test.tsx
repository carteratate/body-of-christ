// @vitest-environment jsdom

import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoadingAnimation } from "./LoadingAnimation";

const baseProps = {
  collections: ["bible"],
  quota: 3,
  onFiltersReady: vi.fn(),
  onReadyToShow: vi.fn(),
  onFadeComplete: vi.fn(),
};

describe("LoadingAnimation presentation milestones", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("announces filters-ready at exactly 3.2 seconds", () => {
    render(
      <LoadingAnimation
        {...baseProps}
        retrievalStarted={false}
        isQueryDone={false}
      />,
    );

    act(() => vi.advanceTimersByTime(3_199));
    expect(baseProps.onFiltersReady).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(baseProps.onFiltersReady).toHaveBeenCalledOnce();
  });

  it("stretches at the retrieval gate until retrieval starts", () => {
    const view = render(
      <LoadingAnimation
        {...baseProps}
        retrievalStarted={false}
        isQueryDone
      />,
    );

    act(() => vi.advanceTimersByTime(30_000));
    expect(baseProps.onReadyToShow).not.toHaveBeenCalled();

    view.rerender(
      <LoadingAnimation
        {...baseProps}
        retrievalStarted
        isQueryDone
      />,
    );
    act(() => vi.advanceTimersByTime(10_049));
    expect(baseProps.onReadyToShow).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(baseProps.onReadyToShow).toHaveBeenCalledOnce();
  });

  it("stretches at result readiness, then reveals beneath the complete fade", () => {
    const view = render(
      <LoadingAnimation
        {...baseProps}
        retrievalStarted
        isQueryDone={false}
      />,
    );
    const overlay = view.container.firstElementChild as HTMLElement;

    act(() => vi.advanceTimersByTime(30_000));
    expect(baseProps.onReadyToShow).not.toHaveBeenCalled();
    expect(overlay.style.opacity).toBe("1");

    view.rerender(
      <LoadingAnimation
        {...baseProps}
        retrievalStarted
        isQueryDone
      />,
    );
    act(() => vi.advanceTimersByTime(199));
    expect(baseProps.onReadyToShow).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(baseProps.onReadyToShow).toHaveBeenCalledOnce();
    expect(overlay.style.opacity).toBe("0");
    expect(baseProps.onFadeComplete).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1_499));
    expect(baseProps.onFadeComplete).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(baseProps.onFadeComplete).toHaveBeenCalledOnce();
  });
});
