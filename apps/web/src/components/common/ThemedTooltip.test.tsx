// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemedTooltip } from "./ThemedTooltip";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("ThemedTooltip", () => {
  it("suppresses the causal touch focus but allows later keyboard focus and Escape dismissal", async () => {
    vi.useFakeTimers();
    render(
      <ThemedTooltip label="Helpful context">
        <button type="button">Action</button>
      </ThemedTooltip>,
    );
    const button = screen.getByRole("button", { name: "Action" });

    fireEvent.pointerDown(button, { pointerType: "touch" });
    fireEvent.focus(button);
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.blur(button);
    await vi.advanceTimersByTimeAsync(500);

    fireEvent.focus(button);
    expect(screen.getByRole("tooltip").textContent).toBe("Helpful context");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("closes the previous keyboard tooltip immediately when focus moves", async () => {
    render(
      <div>
        <ThemedTooltip label="First description"><button type="button">First</button></ThemedTooltip>
        <ThemedTooltip label="Second description"><button type="button">Second</button></ThemedTooltip>
      </div>,
    );

    const first = screen.getByRole("button", { name: "First" });
    const second = screen.getByRole("button", { name: "Second" });
    fireEvent.focus(first);
    expect(screen.getByRole("tooltip").textContent).toBe("First description");
    fireEvent.blur(first, { relatedTarget: second });
    fireEvent.focus(second);
    expect(screen.getAllByRole("tooltip")).toHaveLength(1);
    expect(screen.getByRole("tooltip").textContent).toBe("Second description");
  });
});
