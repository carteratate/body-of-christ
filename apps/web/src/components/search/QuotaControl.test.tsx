// @vitest-environment jsdom

import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { COLLECTIONS } from "@/lib/collections";
import { QuotaControl } from "./QuotaControl";

function rgb(hex: string): number[] {
  return [1, 3, 5].map((index) => Number.parseInt(hex.slice(index, index + 2), 16));
}

function mix(a: number[], b: number[], weight: number): number[] {
  return a.map((channel, index) => channel * weight + b[index] * (1 - weight));
}

function luminance(color: number[]): number {
  const [red, green, blue] = color.map((channel) => {
    const normalized = channel / 255;
    return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
  });
  return red * 0.2126 + green * 0.7152 + blue * 0.0722;
}

function contrast(a: number[], b: number[]): number {
  const first = luminance(a);
  const second = luminance(b);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

describe("QuotaControl", () => {
  afterEach(() => {
    cleanup();
    document.documentElement.removeAttribute("data-theme");
  });

  it("offers 10 only for one valid focused collection", () => {
    const view = render(<QuotaControl value={5} onChange={vi.fn()} focusedCollection="bible" />);

    expect(screen.getAllByRole("button").map((button) => button.textContent)).toEqual(["3", "4", "5", "10"]);
    expect(screen.getByRole("button", { name: "10 passages per source" }).getAttribute("aria-pressed")).toBe("false");

    view.rerender(<QuotaControl value={5} onChange={vi.fn()} focusedCollection={null} />);
    expect(screen.queryByRole("button", { name: "10 passages per source" })).toBeNull();

    view.rerender(<QuotaControl value={5} onChange={vi.fn()} focusedCollection="retired" />);
    expect(screen.queryByRole("button", { name: "10 passages per source" })).toBeNull();
  });

  it("uses the collection color, four-pixel gold boundary, and a high-contrast numeral", () => {
    const view = render(<QuotaControl value={5} onChange={vi.fn()} focusedCollection="bible" />);
    const ten = screen.getByRole("button", { name: "10 passages per source" });

    expect(ten.style.getPropertyValue("--focused-quota-color")).toBe("var(--color-collection-bible)");
    expect(ten.getAttribute("data-selected")).toBe("false");
    expect(ten.className).toContain("border-[4px]");
    expect(ten.className).toContain("text-brand-primary");

    view.rerender(<QuotaControl value={10} onChange={vi.fn()} focusedCollection="bible" />);
    expect(ten.getAttribute("aria-pressed")).toBe("true");
    expect(ten.getAttribute("data-selected")).toBe("true");
    expect(ten.className).toContain("text-brand-contrast-dark");
  });

  it("uses the light contrast token for the dark apostolic-exhortations fill", () => {
    render(<QuotaControl value={10} onChange={vi.fn()} focusedCollection="apostolic-exhortations" />);

    expect(screen.getByRole("button", { name: "10 passages per source" }).className)
      .toContain("text-brand-contrast-light");
  });

  it("adds a subtle numeral-only contrast lift for selected Papal Documents", () => {
    const view = render(<QuotaControl value={10} onChange={vi.fn()} focusedCollection="papal-documents" />);
    const ten = screen.getByRole("button", { name: "10 passages per source" });

    expect(ten.className).toContain("themeSensitiveNumeral");
    expect(ten.querySelector("span")?.className).toContain("papalNumeral");

    view.rerender(<QuotaControl value={5} onChange={vi.fn()} focusedCollection="papal-documents" />);
    expect(ten.querySelector("span")?.className).not.toContain("papalNumeral");
  });

  it("keeps the numeral above 4.5:1 in both themes and both fill states", () => {
    const themes = [
      { label: "dark", surface: rgb("#172232"), primary: rgb("#EAE6DC") },
      { label: "light", surface: rgb("#e3dbc8"), primary: rgb("#1a1610") },
    ];

    for (const collection of COLLECTIONS) {
      for (const theme of themes) {
        const unselected = mix(rgb(collection.hex), theme.surface, 0.3);
        expect(contrast(unselected, theme.primary), `${collection.key} unselected`).toBeGreaterThanOrEqual(4.5);

        let selected = mix(rgb(collection.hex), theme.surface, 0.85);
        if (collection.key === "papal-documents") selected = mix(rgb("#ffffff"), selected, 0.03);
        const themeSensitive = collection.key === "canon-law" || collection.key === "papal-documents";
        const useLightNumeral = collection.key === "apostolic-exhortations"
          || (themeSensitive && theme.label === "dark");
        const numeral = useLightNumeral ? rgb("#ffffff") : rgb("#000000");
        expect(contrast(selected, numeral), `${collection.key} selected`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("pulses the ten button without adding a separate outline", async () => {
    const user = userEvent.setup();
    render(<QuotaControl value={5} onChange={vi.fn()} focusedCollection="bible" />);

    const ten = screen.getByRole("button", { name: "10 passages per source" });
    await user.click(ten);

    expect(ten.children).toHaveLength(1);
    expect(ten.firstElementChild?.textContent).toBe("10");
  });

  it("plays one attached pulse only when 10 is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const view = render(<QuotaControl value={5} onChange={onChange} focusedCollection="bible" />);

    const ten = screen.getByRole("button", { name: "10 passages per source" });
    await user.click(ten);
    expect(onChange).toHaveBeenCalledWith(10);
    expect(ten.className).toContain("attachedPulse");

    view.rerender(<QuotaControl value={10} onChange={onChange} focusedCollection="bible" />);
    onChange.mockClear();
    await user.click(ten);
    expect(onChange).not.toHaveBeenCalled();
    expect(ten.className).toContain("attachedPulse");

    await user.click(screen.getByRole("button", { name: "5 passages per source" }));
    expect(ten.className).not.toContain("attachedPulse");

    view.unmount();
    onChange.mockClear();
    render(<QuotaControl value={10} onChange={onChange} focusedCollection="bible" />);
    await user.click(screen.getByRole("button", { name: "5 passages per source" }));
    expect(onChange).toHaveBeenCalledWith(5);
    expect(screen.getByRole("button", { name: "10 passages per source" }).className)
      .not.toContain("attachedPulse");
  });

  it("keeps keyboard focus on the selected standard quota when 10 leaves", () => {
    const view = render(<QuotaControl value={10} onChange={vi.fn()} focusedCollection="bible" />);
    screen.getByRole("button", { name: "10 passages per source" }).focus();

    view.rerender(<QuotaControl value={5} onChange={vi.fn()} focusedCollection={null} />);

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "5 passages per source" }));
  });

  it("does not revive a pulse after focused eligibility leaves and returns", async () => {
    const user = userEvent.setup();
    const view = render(<QuotaControl value={5} onChange={vi.fn()} focusedCollection="bible" />);
    await user.click(screen.getByRole("button", { name: "10 passages per source" }));

    view.rerender(<QuotaControl value={5} onChange={vi.fn()} focusedCollection={null} />);
    await act(() => Promise.resolve());
    view.rerender(<QuotaControl value={5} onChange={vi.fn()} focusedCollection="bible" />);

    expect(screen.getByRole("button", { name: "10 passages per source" }).className)
      .not.toContain("attachedPulse");
  });
});
