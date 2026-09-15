// @vitest-environment jsdom

import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchPage } from "./SearchPage";

const apiMocks = vi.hoisted(() => ({ updatePreferences: vi.fn() }));
const appMocks = vi.hoisted(() => ({ setPreferences: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({
    token: "test-token",
    userId: "test-user",
    preferences: {
      default_collections: ["bible"],
      preferred_translation: "CPDV",
      default_quota: 5,
      last_standard_quota: 5,
      theme: "dark",
    },
    setPreferences: appMocks.setPreferences,
    searchKey: 0,
    searches: [],
    setActiveSearchId: vi.fn(),
    setPendingSearch: vi.fn(),
    clearPendingSearch: vi.fn(),
    refreshSearches: vi.fn(),
  }),
}));

vi.mock("@/components/layout/guestGate", () => ({ useGuestGate: () => null }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  updatePreferences: apiMocks.updatePreferences,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("search default save status", () => {
  it("does not save or announce defaults just because the page opened", async () => {
    apiMocks.updatePreferences.mockImplementation(async (_token, value) => ({ ...value, theme: "dark" }));
    render(<StrictMode><SearchPage /></StrictMode>);

    await act(async () => { await Promise.resolve(); });

    expect(apiMocks.updatePreferences).not.toHaveBeenCalled();
    expect(screen.queryByText("Default saved")).toBeNull();
  });

  it("waits before showing a saving status, then confirms the default", async () => {
    let finishSave!: () => void;
    apiMocks.updatePreferences.mockImplementation((_token, value) => new Promise((resolve) => {
      finishSave = () => resolve({ ...value, theme: "dark" });
    }));
    render(<SearchPage />);

    fireEvent.click(screen.getByRole("button", { name: "10 passages per source" }));

    expect(screen.queryByText("Saving default…")).toBeNull();
    expect(await screen.findByText("Saving default…")).toBeTruthy();
    await act(async () => finishSave());
    expect(await screen.findByText("Default saved")).toBeTruthy();
  });

  it("briefly confirms a saved focused default beneath the selector", async () => {
    apiMocks.updatePreferences.mockImplementation(async (_token, value) => ({ ...value, theme: "dark" }));
    render(<SearchPage />);

    fireEvent.click(screen.getByRole("button", { name: "10 passages per source" }));

    expect(await screen.findByText("Default saved")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("Default saved")).toBeNull(), { timeout: 2500 });
    expect(screen.queryByText("Your search defaults could not be saved. Try again.")).toBeNull();
  });

  it("shows a failed default save beneath the quota selector without a popup or retry prompt", async () => {
    apiMocks.updatePreferences.mockRejectedValue(new Error("Preferences request failed"));
    render(<SearchPage />);

    fireEvent.click(screen.getByRole("button", { name: "10 passages per source" }));

    const status = await screen.findByText("Default not saved");
    const selector = screen.getByRole("group", { name: "Results per source" });
    expect(selector.compareDocumentPosition(status) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText("Your search defaults could not be saved. Try again.")).toBeNull();
    expect(screen.queryByText(/retry/i)).toBeNull();
  });
});
