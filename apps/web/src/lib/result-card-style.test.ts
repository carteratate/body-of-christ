// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_RESULT_CARD_STYLE,
  RESULT_CARD_STYLE_KEY,
  parseResultCardStyle,
  readResultCardStyle,
  resetResultCardStyleForTests,
  setResultCardStyle,
  useResultCardStyle,
} from "./result-card-style";

beforeEach(() => {
  localStorage.clear();
  resetResultCardStyleForTests();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("result card style", () => {
  it("defaults to the collection tint", () => {
    expect(DEFAULT_RESULT_CARD_STYLE).toBe("tint");
    expect(readResultCardStyle()).toBe("tint");
    expect(renderHook(() => useResultCardStyle()).result.current).toBe("tint");
  });

  it("reads only the two known styles", () => {
    expect(parseResultCardStyle("plain")).toBe("plain");
    expect(parseResultCardStyle("tint")).toBe("tint");
    expect(parseResultCardStyle("striped")).toBe("tint");
    expect(parseResultCardStyle(null)).toBe("tint");
    expect(parseResultCardStyle(undefined)).toBe("tint");
  });

  it("keeps a guest's choice in this browser", () => {
    localStorage.setItem(RESULT_CARD_STYLE_KEY, "plain");
    expect(readResultCardStyle()).toBe("plain");
  });

  it("stores a change and tells the cards", () => {
    const { result } = renderHook(() => useResultCardStyle());
    act(() => setResultCardStyle("plain"));
    expect(result.current).toBe("plain");
    expect(localStorage.getItem(RESULT_CARD_STYLE_KEY)).toBe("plain");
    act(() => setResultCardStyle("tint"));
    expect(result.current).toBe("tint");
    expect(localStorage.getItem(RESULT_CARD_STYLE_KEY)).toBe("tint");
  });

  it("falls back to the tint when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readResultCardStyle()).toBe("tint");
    expect(() => setResultCardStyle("plain")).not.toThrow();
    expect(readResultCardStyle()).toBe("plain");
  });
});

describe("result card style across tabs", () => {
  it("follows a change another tab stores", () => {
    const { result } = renderHook(() => useResultCardStyle());
    expect(result.current).toBe("tint");
    act(() => {
      localStorage.setItem(RESULT_CARD_STYLE_KEY, "plain");
      window.dispatchEvent(new StorageEvent("storage", { key: RESULT_CARD_STYLE_KEY, newValue: "plain" }));
    });
    expect(result.current).toBe("plain");
  });

  it("ignores other keys", () => {
    const { result } = renderHook(() => useResultCardStyle());
    act(() => {
      localStorage.setItem(RESULT_CARD_STYLE_KEY, "plain");
      window.dispatchEvent(new StorageEvent("storage", { key: "theocorpus-theme", newValue: "light" }));
    });
    expect(result.current).toBe("tint");
  });

  it("reads storage afresh when cards mount after a change went unwatched", () => {
    expect(readResultCardStyle()).toBe("tint");
    localStorage.setItem(RESULT_CARD_STYLE_KEY, "plain");
    expect(renderHook(() => useResultCardStyle()).result.current).toBe("plain");
  });
});
