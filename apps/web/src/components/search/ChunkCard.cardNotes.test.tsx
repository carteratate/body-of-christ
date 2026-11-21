// @vitest-environment jsdom

// Corpus cleanup 4.4: the notes under an opened passage in three slots when the API
// sends a `card`, and today's lines when it does not.

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChunkCard } from "./ChunkCard";
import type { ChunkResult } from "@/lib/api";

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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const VATICAN = "© Dicastery for Communication – Libreria Editrice Vaticana";

function result(source: Partial<ChunkResult["source"]> = {}): ChunkResult {
  return {
    chunk_id: "00000000-0000-0000-0000-000000000001",
    content: "After the reception of baptism, the following are enrolled in another Church…",
    source: {
      collection: "canon-law",
      document_title: "Code of Canon Law",
      author: null,
      reference: "Code of Canon Law, Can. 112",
      document_id: "00000000-0000-0000-0000-000000000002",
      position: 1,
      anchor: "can/112",
      ...source,
    },
    reranker_score: 0.82,
    explanation: "Relevant",
  };
}

async function open(item: ChunkResult) {
  render(<ChunkCard result={item} index={0} searchId="00000000-0000-0000-0000-000000000003" token="token" />);
  await userEvent.click(screen.getByRole("button", { expanded: false }));
}

const CANON_112 = {
  facts: { translation: "Vatican English", source_credit: VATICAN },
  text_status: "unofficial_english" as const,
  official_latin_url: "https://www.vatican.va/latin.html",
  card: {
    cautions: [{
      kind: "wording" as const,
      text: "An unofficial English translation (L’Osservatore Romano). The Latin text is official.",
      link: { label: "The Latin text is official.", href: "https://www.vatican.va/latin.html" },
    }],
    record: [],
    notice: VATICAN,
  },
};

describe("the 4.4 card under an opened passage", () => {
  it("shows a caution opened by its kind, with the Latin linked in place, then the notice", async () => {
    await open(result(CANON_112));
    const cautions = screen.getByTestId("card-cautions");
    expect(within(cautions).getByText("Wording")).toBeTruthy();
    const link = within(cautions).getByRole("link", { name: /The Latin text is official/ });
    expect(link.getAttribute("href")).toBe("https://www.vatican.va/latin.html");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(screen.getByTestId("card-notice").textContent).toBe(VATICAN);
    // Today's lines are gone: no "Translation:" line and no second translator.
    expect(screen.queryByText(/Translation: Vatican English/)).toBeNull();
    expect(screen.queryByTestId("passage-facts")).toBeNull();
    expect(screen.queryByTestId("card-record")).toBeNull();
  });

  it("joins the record line with dots and never shows the stored source credit", async () => {
    await open(result({
      collection: "encyclicals", document_title: "Ineffabilis Deus",
      facts: { genre: "apostolic-constitution", form: "bull", source_credit: "Translation from Official Documents (1855)" },
      card: { cautions: [], record: ["Apostolic constitution, issued as a bull", "Translation from Official Documents (1855)", "scanned"], notice: null },
    }));
    expect(screen.getByTestId("card-record").textContent)
      .toBe("Apostolic constitution, issued as a bull · Translation from Official Documents (1855) · scanned");
    expect(screen.queryByTestId("card-cautions")).toBeNull();
    expect(screen.queryByTestId("card-notice")).toBeNull();
    expect(screen.queryByText("Apostolic constitution · issued as a bull")).toBeNull();
  });

  it("puts nothing under a psalm whose card is empty, though its facts carry a credit", async () => {
    await open(result({
      collection: "bible", document_title: "Psalms",
      facts: { translation: "WEB-C", source_credit: "Public domain. Sourced via eBible.org" },
      card: { cautions: [], record: [], notice: null },
    }));
    expect(screen.queryByTestId("card-notes")).toBeNull();
    expect(screen.queryByText(/eBible/)).toBeNull();
  });

  it("stacks cautions of different kinds in one panel", async () => {
    await open(result({
      collection: "encyclicals",
      card: {
        cautions: [
          { kind: "incomplete", text: "Abridged by the translator." },
          { kind: "authority", text: "Superseded by a later text." },
        ],
        record: ["Encyclical"], notice: null,
      },
    }));
    const items = within(screen.getByTestId("card-cautions")).getAllByTestId("card-caution");
    expect(items.map((item) => item.textContent)).toEqual([
      "IncompleteAbridged by the translator.", "AuthoritySuperseded by a later text.",
    ]);
  });

  it("renders today's lines when the API sends no card", async () => {
    await open(result({
      collection: "church-fathers",
      facts: { translation: "Ante-Nicene Fathers (1885-1896)", source_credit: "Sourced via CCEL.org" },
    }));
    const facts = screen.getByTestId("passage-facts");
    expect(within(facts).getByText("Translation: Ante-Nicene Fathers (1885-1896)")).toBeTruthy();
    expect(within(facts).getByText("Sourced via CCEL.org")).toBeTruthy();
    expect(screen.queryByTestId("card-notes")).toBeNull();
  });
});

describe("copying a passage", () => {
  function clipboard() {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    return writeText;
  }

  it("keeps only the required notice when the passage has a card", async () => {
    const writeText = clipboard();
    await open(result(CANON_112));
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));
    expect(writeText.mock.calls[0][0].endsWith(`\n\n${VATICAN}`)).toBe(true);
  });

  it("drops a source credit that is not a required notice", async () => {
    const writeText = clipboard();
    await open(result({
      collection: "church-fathers",
      facts: { source_credit: "Sourced via CCEL.org" },
      card: { cautions: [], record: ["Ante-Nicene Fathers (1885–1896)"], notice: null },
    }));
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));
    expect(writeText.mock.calls[0][0]).not.toContain("CCEL");
  });

  it("keeps today's credit without a card", async () => {
    const writeText = clipboard();
    await open(result({ collection: "church-fathers", facts: { source_credit: "Sourced via CCEL.org" } }));
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));
    expect(writeText.mock.calls[0][0].endsWith("\n\nSourced via CCEL.org")).toBe(true);
  });
});
