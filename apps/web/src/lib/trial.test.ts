// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  clearGuestPreferenceDraft,
  getGuestPreferenceDraft,
  saveGuestPreferenceDraft,
} from "./trial";


describe("guest preference draft", () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    });
  });

  it("starts with the six current collections and quota 3", () => {
    expect(getGuestPreferenceDraft()).toEqual({
      preferred_translation: "CPDV",
      default_collections: [
        "bible", "catechism", "church-fathers", "summa", "councils", "encyclicals",
      ],
      default_quota: 3,
      last_standard_quota: 3,
    });
  });

  it("stores and clears all four transferable fields", () => {
    saveGuestPreferenceDraft({
      preferred_translation: "douay-rheims",
      default_collections: ["bible"],
      default_quota: 10,
      last_standard_quota: 5,
    });

    expect(getGuestPreferenceDraft()).toEqual({
      preferred_translation: "douay-rheims",
      default_collections: ["bible"],
      default_quota: 10,
      last_standard_quota: 5,
    });

    clearGuestPreferenceDraft();
    expect(getGuestPreferenceDraft().default_quota).toBe(3);
  });
});
