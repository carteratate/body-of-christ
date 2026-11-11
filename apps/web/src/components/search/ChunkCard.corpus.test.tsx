// @vitest-environment jsdom

// Corpus cleanup 2.4b: what a result card shows of the API's new optional fields, and
// that a result without them renders exactly as before.

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChunkCard, mobileCitation, primaryCitation } from "./ChunkCard";
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

const DOC = "00000000-0000-0000-0000-000000000002";

function result(overrides: Partial<ChunkResult> = {}, source: Partial<ChunkResult["source"]> = {}): ChunkResult {
  return {
    chunk_id: "00000000-0000-0000-0000-000000000001",
    content: "Wherefore, O Greeks, I deem it right…",
    source: {
      collection: "church-fathers",
      document_title: "Hortatory Address to the Greeks",
      author: "Justin Martyr",
      reference: "Justin Martyr — Hortatory Address to the Greeks, Chapter I",
      document_id: DOC,
      position: 1,
      anchor: "hortatory/1",
      ...source,
    },
    reranker_score: 0.82,
    explanation: "Relevant",
    ...overrides,
  };
}

function renderCard(item: ChunkResult, props: Partial<React.ComponentProps<typeof ChunkCard>> = {}) {
  return render(<ChunkCard result={item} index={0} searchId="00000000-0000-0000-0000-000000000003" token="token" {...props} />);
}

async function expand() {
  await userEvent.click(screen.getByRole("button", { expanded: false }));
}

describe("result card header (collapsed)", () => {
  it("shows the attribution, date and certainty tag, and never the source credit", () => {
    renderCard(result({}, {
      author: "Pseudo-Justin",
      facts: {
        certainty: "pseudonymous", date_display: "3rd century", source_credit: "Sourced via CCEL.org",
        translation: "Translated by Marcus Dods", notes: "Not by Justin Martyr.",
      },
    }));
    const header = screen.getByRole("button", { expanded: false });
    expect(within(header).getAllByText("Pseudo-Justin · 3rd century").length).toBeGreaterThan(0);
    expect(within(header).getAllByText("pseudonymous").length).toBeGreaterThan(0);
    expect(screen.queryByText(/CCEL/)).toBeNull();
    expect(screen.queryByText(/Not by Justin Martyr/)).toBeNull();
    expect(screen.queryByText(/Marcus Dods/)).toBeNull();
  });

  it("shows a quoted Father on a Catena passage", () => {
    renderCard(result({}, {
      collection: "medieval", author: "Thomas Aquinas", document_title: "Catena Aurea", reference: "Catena Aurea, Matthew 5",
      passage_author: "Chrysostom",
    }));
    expect(screen.getAllByText("Chrysostom, quoted in Thomas Aquinas's Catena Aurea").length).toBeGreaterThan(0);
  });

  it("takes the Bible translation badge from facts", () => {
    renderCard(result({}, {
      collection: "bible", author: null, document_title: "Genesis", reference: "Genesis 1:1",
      facts: { translation: "WEB-C" },
    }));
    expect(screen.getAllByText("Bible · WEB-C").length).toBeGreaterThan(0);
  });
});

describe("result card body (opened)", () => {
  it("shows the translation, then the notes, then the credit, last", async () => {
    renderCard(result({}, {
      author: "Justin Martyr",
      facts: {
        certainty: "disputed", attribution_note: "Authorship disputed; Heimgartner (2001) assigns it to Athenagoras.",
        notes: "A volume note.", translation: "Translated by Marcus Dods", source_credit: "Sourced via CCEL.org",
      },
      passage_note: "A passage note.",
    }));
    await expand();
    const facts = screen.getByTestId("passage-facts");
    const lines = [...facts.querySelectorAll("p")].map((p) => p.textContent);
    expect(lines).toEqual([
      "Translated by Marcus Dods",
      "Authorship disputed; Heimgartner (2001) assigns it to Athenagoras.",
      "A volume note.",
      "A passage note.",
      "Sourced via CCEL.org",
    ]);
  });

  it("names a translation code in full", async () => {
    renderCard(result({}, { collection: "bible", author: null, facts: { translation: "WEB-C" } }));
    await expand();
    expect(screen.getByText("Translation: World English Bible, Catholic Edition")).toBeTruthy();
  });

  it("says a non-English passage is not in search", async () => {
    renderCard(result({}, { language: "la" }));
    await expand();
    expect(screen.getByText("This passage is in Latin; it is not included in search.")).toBeTruthy();
  });

  it("marks a moved passage and shows its new text", async () => {
    renderCard(result({
      status: "moved",
      content: "The new text",
      redirect: { kind: "renumbered", document_id: DOC, chunk_id: "new" },
    }));
    await expand();
    expect(screen.getByText("This passage was renumbered in a corpus update.")).toBeTruthy();
    expect(screen.getByText("The new text")).toBeTruthy();
  });

  it("copies the attributed author, so a Pseudo-Justin passage is not credited to Justin", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderCard(result({}, { author: "Pseudo-Justin", facts: { certainty: "pseudonymous" } }));
    await expand();
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));
    expect(writeText.mock.calls[0][0]).toContain("(Pseudo-Justin)");
    expect(writeText.mock.calls[0][0]).not.toContain("Justin Martyr");
  });
});

describe("removed passage", () => {
  const removed = result({
    status: "removed",
    content: "",
    tombstone: {
      entity: "passage", rule: "A", reason_code: "rule-a",
      public_reason: "Removed because the Second Council of Constantinople (553) condemned Origen by name.",
      church_act: "Second Council of Constantinople, anathema 11, 553",
      retired_at: "2026-12-01T00:00:00Z",
      title: "De Principiis", author: "Origen", reference: "Origen — De Principiis, Book I · Chapter I",
    },
  }, { document_title: "De Principiis", author: "Origen", reference: "Origen — De Principiis, Book I · Chapter I" });

  it("stays collapsed like its neighbours, with Removed where the score would be", () => {
    renderCard(removed);
    const card = screen.getByTestId("removed-chunk-card");
    expect(card.getAttribute("style")).toContain("background: rgba(");
    expect(within(card).getAllByText("Origen").length).toBeGreaterThan(0);
    expect(within(card).getAllByText("De Principiis, Book I · Chapter I").length).toBeGreaterThan(0);
    expect(within(card).getByText("Removed")).toBeTruthy();
    expect(screen.queryByText(/condemned Origen by name/)).toBeNull();
  });

  it("shows the reason and Church act once opened, and no text or actions", async () => {
    renderCard(removed);
    await expand();
    const card = screen.getByTestId("removed-chunk-card");
    expect(within(card).getByText("Removed from TheoCorpus")).toBeTruthy();
    expect(within(card).getByText(/condemned Origen by name/)).toBeTruthy();
    expect(within(card).getByText("Church act: Second Council of Constantinople, anathema 11, 553")).toBeTruthy();
    expect(within(card).getByRole("link", { name: "Why was this removed?" }).getAttribute("href")).toBe("/about");
    expect(screen.queryByRole("button", { name: /bookmark|Save passage/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /relevant/i })).toBeNull();
    expect(screen.queryByRole("link", { name: "Open in Context" })).toBeNull();
  });

  it("shows a forgery removed on scholarship with no Church act line", async () => {
    renderCard(result({
      status: "removed",
      content: "",
      tombstone: {
        entity: "passage", rule: "B", reason_code: "rule-b",
        public_reason: "Removed because most scholars judge this longer version the work of a heterodox compiler, not Ignatius.",
        church_act: null,
        retired_at: "2026-12-01T00:00:00Z",
        title: "Epistle to the Ephesians", author: "Ignatius of Antioch", reference: null,
      },
    }, { document_title: "Epistle to the Ephesians", author: "Ignatius of Antioch", reference: null }));
    await expand();
    const card = screen.getByTestId("removed-chunk-card");
    expect(within(card).getByText(/heterodox compiler/)).toBeTruthy();
    expect(within(card).queryByText(/Church act:/)).toBeNull();
  });

  it("links to where a held text can still be read", async () => {
    renderCard(result({
      status: "removed",
      content: "",
      tombstone: {
        entity: "document", rule: "", reason_code: "awaiting-permission",
        public_reason: "This translation is not available on TheoCorpus at present.",
        read_elsewhere_url: "https://www.papalencyclicals.net/greg16/g16mirar.htm",
        retired_at: "2026-12-01T00:00:00Z", title: "Mirari Vos", author: "Pope Gregory XVI",
      },
    }, { collection: "encyclicals", document_title: "Mirari Vos", author: "Pope Gregory XVI", reference: null }));
    expect(screen.getByText("Not available")).toBeTruthy();
    await expand();
    expect(screen.getByText("Not available on TheoCorpus")).toBeTruthy();
    const link = screen.getByRole("link", { name: /Read it at papalencyclicals.net/ });
    expect(link.getAttribute("href")).toBe("https://www.papalencyclicals.net/greg16/g16mirar.htm");
    expect(screen.getByRole("link", { name: "Why isn't this available?" })).toBeTruthy();
  });

  it("renders as a current card when the removal comes with no reason to show", () => {
    renderCard(result({ status: "removed", tombstone: null }));
    expect(screen.queryByTestId("removed-chunk-card")).toBeNull();
  });
});

describe("citations (Opus-2 B-003, B-011)", () => {
  it("shortens both Summa reference forms on mobile", () => {
    expect(mobileCitation("summa", "Summa Theologiae",
      "Summa Theologiae, First Part, Question 19 - Of the Will of God (Twelve Articles), Article 9 - Whether the will of God is the cause of things?",
      "Thomas Aquinas")).toBe("First Part · Q. 19 · Art. 9");
    expect(mobileCitation("summa", "Summa Theologiae",
      "Summa Theologiae II-II, q. 64, a. 6, co.: Whether it is lawful to kill the innocent?", "Thomas Aquinas"))
      .toBe("II-II · Q. 64 · Art. 6");
    expect(mobileCitation("summa", "Summa Theologiae",
      "Summa Theologiae I, q. 19, a. 9, ad 1: Whether the will of God is the cause of things?", "Thomas Aquinas"))
      .toBe("I · Q. 19 · Art. 9");
    expect(mobileCitation("summa", "Summa Theologiae",
      "Summa Theologiae Suppl., App. 1, q. 1, a. 2, co.: Whether …", "Thomas Aquinas"))
      .toBe("Suppl., App. 1 · Q. 1 · Art. 2");
  });

  it("never doubles a Fathers title on desktop", () => {
    expect(primaryCitation("church-fathers", "City of God", "Augustine — City of God, Book I · Chapter 1", "Augustine"))
      .toBe("City of God, Book I · Chapter 1");
    expect(primaryCitation("church-fathers", "City of God", "City of God, Book I · Chapter 1", "Augustine"))
      .toBe("City of God, Book I · Chapter 1");
    // The registry's author no longer matches the name the reference was built with.
    expect(primaryCitation("church-fathers", "Hortatory Address to the Greeks",
      "Justin Martyr — Hortatory Address to the Greeks, Chapter I", "Pseudo-Justin"))
      .toBe("Hortatory Address to the Greeks, Chapter I");
    expect(primaryCitation("church-fathers", "First Apology", "Chapter VI", "Justin Martyr"))
      .toBe("First Apology, Chapter VI");
    expect(primaryCitation("councils", "Second Council of Lyons", "Second Council of Lyons — II", null))
      .toBe("Second Council of Lyons — II");
  });

  it("shows a Fathers title once in the card", () => {
    renderCard(result());
    expect(screen.getAllByText("Hortatory Address to the Greeks, Chapter I").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Greeks, Justin Martyr/)).toBeNull();
  });
});

describe("a result without the new fields", () => {
  // The HTML these cards rendered before 2.4b, collapsed and opened, recorded from
  // master's ChunkCard. No new field: the card must not change.
  const bible = result({}, {
    collection: "bible", document_title: "Genesis", author: null, reference: "Genesis 1:1", anchor: "genesis-1-1",
  });
  const excerpt = result({}, {
    collection: "catechism", document_title: "Catechism of the Catholic Church", author: "Catholic Church",
    reference: "CCC §1127", anchor: "ccc-1127", unit_label: "§1127",
    reader_access: "excerpt", source_url: "https://www.usccb.org/x", source_credit: "Excerpts from the English translation…",
  });

  it.each([["bible", bible], ["excerpt-only", excerpt]])("renders a %s card as before", async (_, item) => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue("11111111-1111-4111-8111-111111111111");
    const { container } = renderCard(item);
    // React's generated IDs count every earlier render in the file.
    const html = () => container.innerHTML.replace(/_r_[0-9a-z]+_|«r[0-9a-z]+»|:r[0-9a-z]+:/g, "«id»");
    expect(html()).toMatchSnapshot("collapsed");
    await expand();
    expect(html()).toMatchSnapshot("opened");
  });
});
