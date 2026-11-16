// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourcesPage } from "./SourcesPage";
import { navigations } from "@/test/next-link-mock";
import { hasReaderReturnMarker } from "@/lib/readerNavigation";
import type { SourceDocument } from "@/lib/api";

const state = vi.hoisted(() => ({
  token: "user-a",
  listReadingProgress: vi.fn(),
  sources: [] as SourceDocument[],
}));

vi.mock("next/link", () => import("@/test/next-link-mock"));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), prefetch: vi.fn() }) }));
vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({
    token: state.token,
    sources: state.sources,
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
  state.sources = [];
});

afterEach(() => {
  cleanup();
  navigations.length = 0;
  sessionStorage.clear();
});

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
    expect(screen.getAllByRole("link", { name: /User B document/ })).toHaveLength(3);
    expect(screen.queryByText("User B document 3")).toBeNull();
    expect(screen.queryByText("Your recent reading places couldn't be loaded.")).toBeNull();
    await waitFor(() => expect(state.listReadingProgress).toHaveBeenCalledWith("user-b", 3, expect.any(AbortSignal)));
  });
});

describe("SourcesPage reader links", () => {
  it("links rows and Continue Reading to the reader with one stable return key", async () => {
    state.sources = [
      { id: "doc-1", title: "Summa Theologiae", author: "Thomas Aquinas", year: 1274, collection: "summa", translation: null, chunk_count: 10, metadata: {} },
    ] as unknown as SourceDocument[];
    state.listReadingProgress.mockResolvedValue([{
      document_id: "doc-2", chapter_key: "chapter-9", chapter_label: "Chapter 9", anchor: null,
      updated_at: "2026-08-01T12:00:00Z", collection: "catechism", document_title: "Catechism", author: null,
    }]);
    render(<SourcesPage />);

    const resume = await screen.findByRole("link", { name: /Catechism/ });
    const row = screen.getByRole("link", { name: /Summa Theologiae/ });
    const key = new URL((row as HTMLAnchorElement).href).searchParams.get("returnKey");
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
    expect(row.getAttribute("href")).toBe(`/reader/doc-1?from=library&returnKey=${key}`);
    expect(resume.getAttribute("href")).toBe(`/reader/doc-2?from=library&returnKey=${key}&chapter=chapter-9`);
    // Rows prefetch on intent, never on sight.
    expect(row.dataset.prefetch).toBe("false");
    expect(resume.dataset.prefetch).toBe("false");

    resume.click();
    expect(navigations).toEqual([`/reader/doc-2?from=library&returnKey=${key}&chapter=chapter-9`]);
    expect(hasReaderReturnMarker(key, "library")).toBe(true);
  });
});


describe("SourcesPage excerpt-only documents (issue #265)", () => {
  it("lists them, linking to the source instead of the reader", async () => {
    state.sources = [
      { id: "doc-1", title: "Libertas", author: "Pope Leo XIII", year: 1888, collection: "encyclicals", translation: null, chunk_count: 40, metadata: {},
        reader_access: "excerpt", source_url: "https://www.papalencyclicals.net/leo13/l13liber.htm" },
      { id: "doc-2", title: "Rerum Novarum", author: "Pope Leo XIII", year: 1891, collection: "encyclicals", translation: null, chunk_count: 50, metadata: {},
        reader_access: "full" },
    ] as unknown as SourceDocument[];
    state.listReadingProgress.mockResolvedValue([]);
    render(<SourcesPage />);

    const blocked = await screen.findByRole("link", { name: /Libertas/ });
    expect(blocked.getAttribute("href")).toBe("https://www.papalencyclicals.net/leo13/l13liber.htm");
    expect(blocked.getAttribute("target")).toBe("_blank");
    expect(screen.getByRole("link", { name: /Rerum Novarum/ }).getAttribute("href")).toMatch(/^\/reader\/doc-2\?/);
  });
});

describe("SourcesPage Bible book order (C-24)", () => {
  // Every title /v1/sources returns today (read 10 Nov 2026), and the titles the
  // rebuilt Bible gives the books (1.4a, `datapipeline/ingest/bible.py`), which
  // rename "Song of Solomon" to "Song of Songs" at the Phase 4 publish.
  const LIVE = "1 Chronicles|1 Corinthians|1 John|1 Kings|1 Maccabees|1 Peter|1 Samuel|1 Thessalonians|1 Timothy|2 Chronicles|2 Corinthians|2 John|2 Kings|2 Maccabees|2 Peter|2 Samuel|2 Thessalonians|2 Timothy|3 John|Acts|Amos|Baruch|Colossians|Daniel|Deuteronomy|Ecclesiastes|Ephesians|Esther|Exodus|Ezekiel|Ezra|Galatians|Genesis|Habakkuk|Haggai|Hebrews|Hosea|Isaiah|James|Jeremiah|Job|Joel|John|Jonah|Joshua|Jude|Judges|Judith|Lamentations|Leviticus|Luke|Malachi|Mark|Matthew|Micah|Nahum|Nehemiah|Numbers|Obadiah|Philemon|Philippians|Proverbs|Psalms|Revelation|Romans|Ruth|Sirach|Song of Solomon|Titus|Tobit|Wisdom|Zechariah|Zephaniah".split("|");
  const REBUILT = [...LIVE.filter((t) => t !== "Song of Solomon"), "Song of Songs"];

  it("ranks every Bible title, under both names of the Song of Songs", async () => {
    const { bookRank } = await import("./SourcesPage");
    for (const title of [...LIVE, ...REBUILT]) expect(bookRank(title), title).toBeLessThan(73);
    expect(new Set(LIVE.map(bookRank)).size).toBe(73);
    expect(new Set(REBUILT.map(bookRank)).size).toBe(73);
    expect(bookRank("Song of Songs")).toBe(bookRank("Song of Solomon"));
    expect(bookRank("Song of Songs")).toBe(bookRank("Ecclesiastes") + 1);
    expect(bookRank("Unknown Book")).toBe(73);
  });
});

describe("SourcesPage Collection drop-down (issue #392)", () => {
  const VAT2 = ["Sacrosanctum Concilium", "Inter Mirifica", "Lumen Gentium"];
  function doc(id: string, collection: string, title: string, extra: Partial<SourceDocument> = {}) {
    return { id, title, author: null, year: null, collection, translation: null, chunk_count: 10, metadata: {}, ...extra } as unknown as SourceDocument;
  }
  const SOURCES = [
    doc("nicaea", "councils", "Council of Nicaea", { year: 325, metadata: { council_number: 1 } }),
    doc("trent", "councils", "Council of Trent", { year: 1545, metadata: { council_number: 19 } }),
    ...VAT2.map((title, i) => doc(`v2-${i}`, "councils", title, { year: 1963 + i, metadata: { council: "Second Vatican Council" } })),
    doc("gen", "bible", "Genesis", { translation: "DRA" }),
    doc("exo", "bible", "Exodus", { translation: "DRA" }),
    doc("summa", "summa", "Summa Theologiae", { author: "Thomas Aquinas", year: 1274 }),
    doc("rn", "encyclicals", "Rerum Novarum", { author: "Pope Leo XIII", year: 1891 }),
  ];

  beforeEach(() => {
    state.sources = SOURCES;
    state.listReadingProgress.mockResolvedValue([]);
  });

  async function choose(collection: string) {
    render(<SourcesPage />);
    const select = await screen.findByRole("combobox");
    fireEvent.change(select, { target: { value: collection } });
  }

  it("shows the Councils section with Vatican II as one collapsed row", async () => {
    await choose("councils");

    expect(screen.getByText("3 councils · 50 passages")).toBeTruthy();
    const vat2 = screen.getByRole("button", { name: /Second Vatican Council/ });
    expect(vat2.textContent).toContain("1963–1965 · 3 documents");
    for (const title of VAT2) expect(screen.queryByText(title)).toBeNull();
    // Councils in date order, with Vatican II in its place among them.
    const rows = screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(rows.map((t) => t.split(/#|\d{4}/)[0].trim().replace(/[▸▾].*/, "").trim()))
      .toEqual(["Council of Nicaea", "Council of Trent", "Second Vatican Council"]);
    expect(screen.queryByText("Genesis")).toBeNull();
    expect(screen.queryByText("Summa Theologiae")).toBeNull();
    expect(screen.queryByText("Continue Reading")).toBeNull();

    fireEvent.click(vat2);
    for (const title of VAT2) expect(screen.getByRole("link", { name: title })).toBeTruthy();
  });

  it("shows the Bible section with its book grid", async () => {
    await choose("bible");

    expect(screen.getByText("1 translation · 20 passages")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /2 books · DRA/ }));
    expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual(["Genesis", "Exodus"]);
    expect(screen.queryByText("Council of Nicaea")).toBeNull();
  });

  it("shows a generic collection's section with its bubble and counts, and nothing else", async () => {
    await choose("encyclicals");

    expect(screen.getByText("1 document · 10 passages")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Rerum Novarum/ })).toBeTruthy();
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("renders the same section as the full page, and returns to it on All collections", async () => {
    render(<SourcesPage />);
    const select = await screen.findByRole("combobox");
    const fullCouncils = screen.getByText("3 councils · 50 passages").closest("section")!.outerHTML;

    fireEvent.change(select, { target: { value: "councils" } });
    expect(screen.getByText("3 councils · 50 passages").closest("section")!.outerHTML).toBe(fullCouncils);

    fireEvent.change(select, { target: { value: "all" } });
    expect(screen.getByText("1 translation · 20 passages")).toBeTruthy();
    expect(screen.getByText("Summa Theologiae")).toBeTruthy();
  });

  it("keeps the text search's flat list, limited to the chosen collection", async () => {
    // "um" matches Rerum Novarum (encyclicals) as well as two Vatican II documents.
    await choose("councils");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "um" } });

    expect(screen.getByText("2 documents")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Second Vatican Council/ })).toBeNull();
    expect(screen.queryByText(/councils ·/)).toBeNull();
    expect(screen.getAllByRole("link").map((a) => a.textContent?.split(/\d/)[0].trim()))
      .toEqual(["Sacrosanctum Concilium", "Lumen Gentium"]);
  });
});
