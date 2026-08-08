// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChunkCard } from "./ChunkCard";

const mocks = vi.hoisted(() => ({ submitLabel: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ bookmarkIds: {}, setBookmarkForChunk: vi.fn() }),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  submitLabel: mocks.submitLabel,
}));
vi.mock("@/lib/analytics", () => ({
  trackBookmarkCreated: vi.fn(), trackBookmarkDeleted: vi.fn(),
  trackDocumentOpened: vi.fn(), trackExploreMoreClicked: vi.fn(),
}));

beforeEach(() => mocks.submitLabel.mockResolvedValue({ label_id: "label" }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("ChunkCard feedback", () => {
  it("removes the report prompt when a down label is changed to up", async () => {
    render(
      <ChunkCard
        result={{
          chunk_id: "00000000-0000-0000-0000-000000000001",
          content: "A passage",
          source: {
            collection: "bible",
            document_title: "Genesis",
            author: null,
            reference: "Genesis 1:1",
            document_id: "00000000-0000-0000-0000-000000000002",
            position: 1,
            anchor: "genesis-1-1",
          },
          reranker_score: 0.9,
          explanation: "Relevant",
        }}
        index={0}
        searchId="00000000-0000-0000-0000-000000000003"
        token="token"
        onExploreMore={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { expanded: false }));
    await userEvent.click(screen.getByRole("button", { name: "Mark as not relevant" }));
    await screen.findByText("Is there a specific problem with this result?", { exact: false });

    await userEvent.click(screen.getByRole("button", { name: "Mark as relevant" }));
    await waitFor(() => expect(screen.queryByText("Is there a specific problem with this result?", { exact: false })).toBeNull());
    expect(mocks.submitLabel).toHaveBeenNthCalledWith(1, "token", expect.any(String), "down", expect.any(String));
    expect(mocks.submitLabel).toHaveBeenNthCalledWith(2, "token", expect.any(String), "up", expect.any(String));
  });
});
