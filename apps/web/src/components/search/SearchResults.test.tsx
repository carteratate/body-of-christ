// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChunkResult } from "@/lib/api";
import { SearchResults } from "./SearchResults";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ bookmarkIds: {}, setBookmarkForChunk: vi.fn() }),
}));

vi.mock("@/components/layout/guestGate", () => ({ useGuestGate: () => null }));

afterEach(cleanup);

function passage(index: number): ChunkResult {
  return {
    chunk_id: `passage-${index}`,
    content: `Passage ${index}`,
    source: {
      collection: "bible",
      document_title: "Genesis",
      author: null,
      reference: `Genesis ${index}:1`,
      document_id: "00000000-0000-0000-0000-000000000001",
      position: index,
    },
    reranker_score: 0.9,
    explanation: null,
  };
}

describe("focused search result notices", () => {
  it("explains a seven-Passage focused result below its cards without padding", () => {
    render(
      <SearchResults
        results={Array.from({ length: 7 }, (_, index) => passage(index + 1))}
        loading={false}
        searchId="search-1"
        token=""
        submittedCollections={["bible"]}
        visibleCollections={["bible"]}
        outcome="success"
        collectionOutcomes={{ bible: "results" }}
        submittedQuota={10}
        deliveryOutcome="underfilled"
        isGuest
      />,
    );

    const notice = screen.getByText(/only 7 passages met/i);
    const cards = screen.getAllByRole("button", { name: /expand result: bible/i });
    expect(cards).toHaveLength(7);
    expect(cards[6].compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("labels closest-match fallback below the Passage cards", () => {
    render(
      <SearchResults
        results={[passage(1), passage(2), passage(3)]}
        loading={false}
        searchId="search-1"
        token=""
        submittedCollections={["bible"]}
        visibleCollections={["bible"]}
        outcome="success"
        collectionOutcomes={{ bible: "results" }}
        submittedQuota={10}
        deliveryOutcome="minimum_floor"
        isGuest
      />,
    );

    const notice = screen.getByText(/no passages met the usual relevance threshold/i);
    const cards = screen.getAllByRole("button", { name: /expand result: bible/i });
    expect(cards[2].compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(notice.closest('[role="status"]')?.className).toContain("border-brand-accent/50");
  });

  it("reports the count without inventing a reason for an older focused search", () => {
    render(
      <SearchResults
        results={[passage(1)]}
        loading={false}
        searchId="search-1"
        token=""
        submittedCollections={["bible"]}
        visibleCollections={["bible"]}
        outcome="success"
        collectionOutcomes={{ bible: "results" }}
        submittedQuota={10}
        reportedResultCount={7}
        historicalOutcomeUnknown
        isGuest
      />,
    );

    expect(screen.getByText(/saved search returned 7 of the 10/i)).toBeTruthy();
    expect(screen.queryByText(/only 7 passages met/i)).toBeNull();
    expect(screen.queryByText(/no passages met the usual relevance threshold/i)).toBeNull();
  });

  it("does not call a complete ten-Passage search underfilled", () => {
    render(
      <SearchResults
        results={Array.from({ length: 10 }, (_, index) => passage(index + 1))}
        loading={false}
        searchId="search-1"
        token=""
        submittedCollections={["bible"]}
        visibleCollections={["bible"]}
        outcome="success"
        collectionOutcomes={{ bible: "results" }}
        submittedQuota={10}
        reportedResultCount={10}
        deliveryOutcome="complete"
        isGuest
      />,
    );

    expect(screen.getAllByRole("button", { name: /expand result: bible/i })).toHaveLength(10);
    expect(screen.queryByText(/only \d+ passages met/i)).toBeNull();
    expect(screen.queryByText(/closest matches we found/i)).toBeNull();
  });

  it("keeps standard-quota searches free of focused notices", () => {
    render(
      <SearchResults
        results={[passage(1), passage(2)]}
        loading={false}
        searchId="search-1"
        token=""
        submittedCollections={["bible"]}
        visibleCollections={["bible"]}
        outcome="success"
        collectionOutcomes={{ bible: "results" }}
        submittedQuota={5}
        reportedResultCount={2}
        deliveryOutcome="minimum_floor"
        isGuest
      />,
    );

    expect(screen.queryByText(/only \d+ passages met/i)).toBeNull();
    expect(screen.queryByText(/closest matches we found/i)).toBeNull();
  });

  it("uses the original delivered count when some saved Passages are unavailable", () => {
    render(
      <SearchResults
        results={[passage(1)]}
        loading={false}
        searchId="search-1"
        token=""
        submittedCollections={["bible"]}
        visibleCollections={["bible"]}
        outcome="success"
        collectionOutcomes={{ bible: "results" }}
        submittedQuota={10}
        reportedResultCount={7}
        deliveryOutcome="underfilled"
        isGuest
      />,
    );

    expect(screen.getByText(/only 7 passages met/i)).toBeTruthy();
    expect(screen.queryByText(/only 1 passage met/i)).toBeNull();
  });
});
