// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { HeldText, TocResponse } from "@/lib/api";
import { __resetClientCachesForTests } from "@/lib/client-cache";
import { DocumentOverview } from "./DocumentOverview";

const api = vi.hoisted(() => ({ getReadingProgress: vi.fn(), getToc: vi.fn() }));
const session = vi.hoisted(() => ({ token: "token" as string | null, guestToken: "" }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  ...api,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: vi.fn(), push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => ({ get: (key: string) => (key === "from" ? "library" : null) }),
}));
vi.mock("@/lib/trial", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/trial")>(),
  getGuestSessionToken: () => session.guestToken,
}));
vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ token: session.token, mobileNavigationOpen: false, openMobileNavigation: vi.fn() }),
}));

const URL = "https://www.papalencyclicals.net/councils/ecum16.htm";

function held(key: string, label: string, heading: string, after: [string, string] | null): HeldText {
  return { key, label, heading, after_anchor: after?.[0] ?? null, after_chapter_key: after?.[1] ?? null, url: URL };
}

function constance(heldTexts?: HeldText[]): TocResponse {
  return {
    document: {
      id: "constance", collection: "councils", title: "Council of Constance", author: null, year: 1414,
      metadata: {}, chunk_count: 13, held_count: heldTexts?.length,
    },
    chapters: [
      { chapter_key: "s8", chapter_label: "Session 8" },
      { chapter_key: "s13", chapter_label: "Session 13" },
      { chapter_key: "s15", chapter_label: "Session 15" },
    ],
    ...(heldTexts ? { held_texts: heldTexts } : {}),
  };
}

const HELD = [
  held("ht-1", "Session 1", "John XXIII's bull", null),
  held("ht-2", "Session 8", "Sentence against John Wyclif", ["s8/2", "s8"]),
  held("ht-3", "Session 14", "Uniting of the obediences", ["s13/1", "s13"]),
  held("ht-4", "Session 45", "Sentence dissolving the council", ["s15/3", "s15"]),
];

beforeEach(() => {
  __resetClientCachesForTests();
  session.token = "token";
  session.guestToken = "";
  api.getReadingProgress.mockResolvedValue(null);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function cells(): string[] {
  const grid = screen.getByRole("heading", { name: "Choose a section" }).closest("section")!;
  return [...grid.querySelectorAll("button, a")].map((el) => el.textContent ?? "");
}

describe.each([
  ["a signed-in reader", false],
  ["a guest", true],
])("DocumentOverview held texts, for %s", (_who, isGuest) => {
  beforeEach(() => {
    if (isGuest) {
      session.token = null;
      session.guestToken = "guest-1";
    }
  });

  it("places each held text after its section, as a link out with no ordinal", async () => {
    api.getToc.mockResolvedValue(constance(HELD));
    render(<DocumentOverview docId="constance" mobileHeader={null} isGuest={isGuest} />);
    await screen.findByRole("heading", { name: "Council of Constance" });

    expect(cells()).toEqual([
      "Session 1 · John XXIII's bullNot on TheoCorpus at present · Read online(opens in a new tab)",
      "1Session 8",
      "Session 8 · Sentence against John WyclifNot on TheoCorpus at present · Read online(opens in a new tab)",
      "2Session 13",
      "Session 14 · Uniting of the obediencesNot on TheoCorpus at present · Read online(opens in a new tab)",
      "3Session 15",
      "Session 45 · Sentence dissolving the councilNot on TheoCorpus at present · Read online(opens in a new tab)",
    ]);
    const links = screen.getAllByTestId("held-text");
    expect(links).toHaveLength(4);
    for (const link of links) {
      expect(link.tagName).toBe("A");
      expect(link.getAttribute("href")).toBe(URL);
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
    expect(screen.getByText(/13 passages · 3 sections/).textContent).toBe(
      "13 passages · 3 sections · 4 texts read online");
  });
});

describe("DocumentOverview held texts", () => {
  it("shows today's overview when the API sends no held texts", async () => {
    api.getToc.mockResolvedValue(constance());
    render(<DocumentOverview docId="constance" mobileHeader={null} />);
    await screen.findByRole("heading", { name: "Council of Constance" });
    expect(screen.queryAllByTestId("held-text")).toEqual([]);
    expect(cells()).toEqual(["1Session 8", "2Session 13", "3Session 15"]);
    expect(screen.getByText(/13 passages/).textContent).toBe("13 passages · 3 sections");
  });

  it("lets the section search match held headings", async () => {
    const many = Array.from({ length: 12 }, (_, i) => held(`ht-${i}`, `Session ${20 + i}`, `Sentence ${i}`, ["s15/3", "s15"]));
    api.getToc.mockResolvedValue(constance([...many, held("ht-x", "Session 21", "Sentence condemning Jerome of Prague", ["s15/3", "s15"])]));
    render(<DocumentOverview docId="constance" mobileHeader={null} />);
    const search = await screen.findByRole("searchbox", { name: "Search sections" });
    fireEvent.change(search, { target: { value: "jerome" } });
    expect(cells()).toEqual([
      "Session 21 · Sentence condemning Jerome of PragueNot on TheoCorpus at present · Read online(opens in a new tab)"]);
    fireEvent.change(search, { target: { value: "session 13" } });
    expect(cells()).toEqual(["2Session 13"]);
  });

  it("counts mixed cells as entries when paging", async () => {
    const many = Array.from({ length: 30 }, (_, i) => held(`ht-${i}`, `Session ${20 + i}`, `Text ${i}`, ["s15/3", "s15"]));
    api.getToc.mockResolvedValue(constance(many));
    render(<DocumentOverview docId="constance" mobileHeader={null} />);
    expect(await screen.findByText("Showing 30 of 33 entries")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show more entries" })).toBeTruthy();
  });

  it("lists held texts under a contents tree", async () => {
    api.getToc.mockResolvedValue({
      ...constance([HELD[0]]),
      contents: [{ key: "I", kind: "part", label: "First Part", short_label: "I", chapter_key: "s8", anchor: null, range_label: null, children: [] }],
    });
    render(<DocumentOverview docId="constance" mobileHeader={null} />);
    const heading = await screen.findByRole("heading", { name: "Read online" });
    const list = heading.parentElement!;
    expect(within(list).getByTestId("held-text").getAttribute("href")).toBe(URL);
  });
});

describe("DocumentOverview chapter batches", () => {
  function book(collection: string, title: string, count: number, label: (n: number) => string): TocResponse {
    return {
      document: { id: title.toLowerCase(), collection, title, author: null, year: null, metadata: {}, chunk_count: count },
      chapters: Array.from({ length: count }, (_, i) => ({ chapter_key: `c${i + 1}`, chapter_label: label(i + 1) })),
    };
  }

  it("shows every chapter of a Bible book with more than 30, and no Show more", async () => {
    api.getToc.mockResolvedValue(book("bible", "Psalms", 150, (n) => `Psalm ${n}`));
    render(<DocumentOverview docId="psalms" mobileHeader={null} />);
    await screen.findByRole("heading", { name: "Psalms" });

    const chapterCells = screen.getAllByRole("button", { name: /^Psalms chapter \d+$/ });
    expect(chapterCells).toHaveLength(150);
    expect(chapterCells.at(-1)?.textContent).toBe("150");
    expect(screen.queryByRole("button", { name: /Show more/ })).toBeNull();
    expect(screen.queryByText(/^Showing /)).toBeNull();

    // The chapter search still narrows the boxes.
    fireEvent.change(screen.getByRole("searchbox", { name: "Search chapters" }), { target: { value: "Psalm 11" } });
    expect(screen.getAllByRole("button", { name: /^Psalms chapter \d+$/ }).map((el) => el.textContent))
      .toEqual(["11", "110", "111", "112", "113", "114", "115", "116", "117", "118", "119"]);
  });

  it("still loads a non-Bible document's sections 30 at a time", async () => {
    api.getToc.mockResolvedValue(book("councils", "Council of Trent", 45, (n) => `Session ${n}`));
    render(<DocumentOverview docId="council of trent" mobileHeader={null} />);
    await screen.findByRole("heading", { name: "Council of Trent" });

    const sessions = () => cells().filter((text) => text.includes("Session"));
    expect(sessions()).toHaveLength(30);
    expect(screen.getByText("Showing 30 of 45 sections")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show more sections" }));
    expect(sessions()).toHaveLength(45);
    expect(screen.queryByRole("button", { name: /Show more/ })).toBeNull();
  });
});
