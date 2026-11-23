// @vitest-environment jsdom

import { useState } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppContext } from "@/components/layout/AppShell";
import type { Preferences } from "@/lib/api";
import { RESULT_CARD_STYLE_KEY, readResultCardStyle, resetResultCardStyleForTests } from "@/lib/result-card-style";
import { SettingsPage } from "./SettingsPage";

const mocks = vi.hoisted(() => ({ updatePreferences: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));
vi.mock("next/link", () => import("@/test/next-link-mock"));
vi.mock("@/lib/supabase/client", () => ({ createClient: () => ({ auth: { signOut: vi.fn() } }) }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  updatePreferences: mocks.updatePreferences,
}));

const PREFERENCES: Preferences = {
  preferred_translation: "CPDV",
  default_collections: ["bible"],
  default_quota: 4,
  last_standard_quota: 4,
  theme: "dark",
  result_card_style: "tint",
};

function renderSettings(initial: Preferences = PREFERENCES) {
  let latest = initial;
  function Harness() {
    const [preferences, setPreferences] = useState<Preferences>(initial);
    latest = preferences;
    return (
      <AppContext.Provider value={{ ready: true, token: "token", preferences, setPreferences, preferencesError: false } as never}>
        <SettingsPage />
      </AppContext.Provider>
    );
  }
  render(<Harness />);
  return { current: () => latest };
}

const cardStyleSwitch = () => screen.getByRole("switch", { name: "Toggle plain result cards" });

beforeEach(() => {
  localStorage.clear();
  resetResultCardStyleForTests();
  mocks.updatePreferences.mockReset();
});

afterEach(cleanup);

describe("Settings: result card style", () => {
  it("sits directly below Theme and starts on the collection tint", () => {
    renderSettings();
    const switches = screen.getAllByRole("switch");
    expect(switches.map((s) => s.getAttribute("aria-label"))).toEqual([
      "Toggle light/dark mode",
      "Toggle plain result cards",
    ]);
    expect(screen.getByText("Result card style")).toBeTruthy();
    expect(screen.getByText("Collection tint")).toBeTruthy();
    expect(cardStyleSwitch().getAttribute("aria-checked")).toBe("false");
  });

  it("switches to Plain at once and saves it with the account", async () => {
    mocks.updatePreferences.mockResolvedValue({ ...PREFERENCES, result_card_style: "plain" });
    const settings = renderSettings();

    await userEvent.click(cardStyleSwitch());

    expect(readResultCardStyle()).toBe("plain");
    expect(localStorage.getItem(RESULT_CARD_STYLE_KEY)).toBe("plain");
    expect(mocks.updatePreferences).toHaveBeenCalledWith("token", { result_card_style: "plain" });
    await waitFor(() => expect(settings.current().result_card_style).toBe("plain"));
    expect(screen.getByText("Plain")).toBeTruthy();
    expect(cardStyleSwitch().getAttribute("aria-checked")).toBe("true");
  });

  it("switches back to the collection tint", async () => {
    mocks.updatePreferences.mockResolvedValue(PREFERENCES);
    renderSettings({ ...PREFERENCES, result_card_style: "plain" });

    await userEvent.click(cardStyleSwitch());

    expect(mocks.updatePreferences).toHaveBeenCalledWith("token", { result_card_style: "tint" });
    expect(readResultCardStyle()).toBe("tint");
    await waitFor(() => expect(screen.getByText("Collection tint")).toBeTruthy());
  });

  it("says so when the save fails", async () => {
    mocks.updatePreferences.mockRejectedValue(new Error("offline"));
    renderSettings();

    await userEvent.click(cardStyleSwitch());

    await screen.findByText("Couldn't save it to your account.");
  });

  it("shows this browser's style while the API cannot store one", () => {
    localStorage.setItem(RESULT_CARD_STYLE_KEY, "plain");
    renderSettings({ ...PREFERENCES, result_card_style: null });

    expect(screen.getByText("Plain")).toBeTruthy();
    expect(cardStyleSwitch().getAttribute("aria-checked")).toBe("true");
  });
});
