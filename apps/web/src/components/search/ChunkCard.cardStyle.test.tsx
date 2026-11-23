// @vitest-environment jsdom

import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChunkCard } from "./ChunkCard";
import type { ChunkResult } from "@/lib/api";
import { RESULT_CARD_STYLE_KEY, resetResultCardStyleForTests, setResultCardStyle } from "@/lib/result-card-style";

vi.mock("next/link", () => import("@/test/next-link-mock"));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ bookmarkIds: {}, setBookmarkForChunk: vi.fn() }),
}));
vi.mock("@/lib/analytics", () => ({
  trackBookmarkCreated: vi.fn(), trackBookmarkDeleted: vi.fn(), trackDocumentOpened: vi.fn(),
}));

const RESULT = {
  chunk_id: "00000000-0000-0000-0000-000000000001",
  content: "In the sweat of thy face shalt thou eat bread",
  source: {
    collection: "bible",
    document_title: "Genesis",
    author: null,
    reference: "Genesis 3:19",
    document_id: "00000000-0000-0000-0000-000000000002",
    position: 1,
    anchor: "genesis-3-19",
  },
  reranker_score: 0.72,
  explanation: "Relevant",
} as ChunkResult;

function renderCard(isGuest = false) {
  render(<ChunkCard result={RESULT} index={0} searchId={null} token="" isGuest={isGuest} />);
  const header = screen.getByRole("button", { expanded: false });
  // The card is the header row's parent.
  return { header, card: () => header.parentElement!.parentElement! };
}

async function open(header: HTMLElement) {
  await userEvent.click(header);
  return header.parentElement!;
}

beforeEach(() => {
  localStorage.clear();
  resetResultCardStyleForTests();
});
afterEach(cleanup);

describe("result card style", () => {
  it("draws today's collection tint by default", async () => {
    const { header, card } = renderCard();
    expect(card().style.background).toMatch(/^rgba\(.*0\.32\)$/);
    expect(card().style.border).toMatch(/^1px solid rgba\(.*0\.7\)$/);
    const headerRow = await open(header);
    expect(headerRow.style.borderBottom).toMatch(/^1px solid rgba\(.*0\.25\)$/);
  });

  it("draws a plain card like a saved passage, with the 3px collection border and bar", async () => {
    setResultCardStyle("plain");
    const { header, card } = renderCard();
    expect(card().style.background).toBe("var(--color-brand-surface)");
    expect(card().style.border).toBe("3px solid var(--color-collection-bible)");
    const headerRow = await open(header);
    expect(headerRow.style.borderBottom).toBe("3px solid var(--color-collection-bible)");
  });

  it("redraws when the setting changes", () => {
    const { card } = renderCard();
    act(() => setResultCardStyle("plain"));
    expect(card().style.background).toBe("var(--color-brand-surface)");
    act(() => setResultCardStyle("tint"));
    expect(card().style.background).toMatch(/^rgba\(/);
  });

  it("gives a guest the style this browser last stored", () => {
    localStorage.setItem(RESULT_CARD_STYLE_KEY, "plain");
    const { card } = renderCard(true);
    expect(card().style.background).toBe("var(--color-brand-surface)");
  });

  it("draws the relevance label in the passage's text colour", async () => {
    const { header } = renderCard();
    await open(header);
    const label = screen.getByText("Show why this is relevant (AI generated)");
    expect(label.className).toContain("text-brand-primary");
    expect(label.style.color).toBe("");
  });
});
