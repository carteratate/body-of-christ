// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourcesPage } from "./SourcesPage";

const state = vi.hoisted(() => ({
  token: "user-a",
  listReadingProgress: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({
    token: state.token,
    sources: [],
    sourcesLoading: false,
    sourcesReady: true,
    sourcesError: false,
    reloadSources: vi.fn(),
  }),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  listReadingProgress: state.listReadingProgress,
}));

beforeEach(() => {
  state.token = "user-a";
  state.listReadingProgress.mockReset();
});

afterEach(cleanup);

describe("SourcesPage Continue Reading", () => {
  it("clears a prior user's error after the new user's request succeeds", async () => {
    state.listReadingProgress.mockImplementation(async (token: string) => {
      if (token === "user-a") throw new Error("offline");
      return Array.from({ length: 5 }, (_, index) => ({
        document_id: `doc-b-${index}`,
        chapter_key: `chapter-b-${index}`,
        chapter_label: `Chapter B ${index}`,
        anchor: null,
        updated_at: `2026-08-0${index + 1}T12:00:00Z`,
        collection: "bible",
        document_title: `User B document ${index}`,
        author: null,
      }));
    });

    const view = render(<SourcesPage />);
    await screen.findByText("Your recent reading places couldn't be loaded.");

    state.token = "user-b";
    view.rerender(<SourcesPage />);

    await screen.findByText("User B document 0");
    expect(screen.getAllByRole("button", { name: /User B document/ })).toHaveLength(3);
    expect(screen.queryByText("User B document 3")).toBeNull();
    expect(screen.queryByText("Your recent reading places couldn't be loaded.")).toBeNull();
    await waitFor(() => expect(state.listReadingProgress).toHaveBeenCalledWith("user-b", 3, expect.any(AbortSignal)));
  });
});
