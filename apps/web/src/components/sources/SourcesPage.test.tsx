// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
