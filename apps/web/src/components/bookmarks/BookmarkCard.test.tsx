// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BookmarkCard } from "./BookmarkCard";
import { navigations } from "@/test/next-link-mock";
import { hasReaderReturnMarker } from "@/lib/readerNavigation";
import { trackDocumentOpened } from "@/lib/analytics";

const mocks = vi.hoisted(() => ({ updateBookmarkNote: vi.fn() }));
vi.mock("next/link", () => import("@/test/next-link-mock"));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), prefetch: vi.fn() }) }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api")>(),
  updateBookmarkNote: mocks.updateBookmarkNote,
}));
vi.mock("@/lib/analytics", () => ({
  trackBookmarkDeleted: vi.fn(),
  trackDocumentOpened: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  navigations.length = 0;
  sessionStorage.clear();
});

describe("BookmarkCard action descriptions", () => {
  it("uses themed descriptions rather than native title tooltips", async () => {
    render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: null,
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "catechism",
              document_title: "Catechism of the Catholic Church",
              author: null,
              reference: "CCC §1000",
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: "ccc-1000",
              chapter_key: "ccc-1000-1099",
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={vi.fn()}
        showToast={vi.fn()}
      />,
    );

    const expectedDescriptions = new Map([
      ["Open passage in context", "Open the passage in context to read the surrounding text."],
      ["Remove bookmark", "Remove this passage from Saved Passages."],
      ["Copy passage", "Copy"],
    ]);
    for (const [name, expected] of expectedDescriptions) {
      const action = screen.getByRole(name === "Open passage in context" ? "link" : "button", { name });
      const descriptionId = action.getAttribute("aria-describedby");
      expect(descriptionId).toBeTruthy();
      expect(action.getAttribute("title")).toBeNull();
      action.focus();
      expect((await screen.findByRole("tooltip")).textContent).toBe(expected);
      await userEvent.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    }
    expect(screen.queryByRole("button", { name: "Query more like this" })).toBeNull();
  });

  it("shows an existing passage note immediately with a direct edit action", () => {
    render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: "Use this when discussing the resurrection of the body.",
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "catechism",
              document_title: "Catechism of the Catholic Church",
              author: null,
              reference: "CCC §1000",
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: "ccc-1000",
              chapter_key: "ccc-1000-1099",
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={vi.fn()}
        showToast={vi.fn()}
      />,
    );

    expect(screen.getByText("Note")).toBeTruthy();
    expect(screen.getByText("Use this when discussing the resurrection of the body.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Note" })).toBeNull();
  });

  it("adds a trimmed private note through the inline editor", async () => {
    mocks.updateBookmarkNote.mockResolvedValue({});
    const onNoteUpdated = vi.fn();
    const showToast = vi.fn();
    render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: null,
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "catechism",
              document_title: "Catechism of the Catholic Church",
              author: null,
              reference: "CCC §1000",
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: "ccc-1000",
              chapter_key: "ccc-1000-1099",
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={onNoteUpdated}
        showToast={showToast}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Add a note" }));
    const editor = screen.getByRole("textbox", { name: "Your note" });
    await userEvent.type(editor, "  A useful connection.  ");
    expect(screen.getByText(/Private · 24 \/ 3,000/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() => expect(mocks.updateBookmarkNote).toHaveBeenCalledWith("token", "bookmark-1", "A useful connection."));
    expect(onNoteUpdated).toHaveBeenCalledWith("bookmark-1", "A useful connection.");
    expect(showToast).toHaveBeenCalledWith("Note saved");
  });

  it("borders the whole card in the collection color", () => {
    const { container } = render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: null,
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "catechism",
              document_title: "Catechism of the Catholic Church",
              author: null,
              reference: "CCC §1000",
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: "ccc-1000",
              chapter_key: "ccc-1000-1099",
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={vi.fn()}
        showToast={vi.fn()}
      />,
    );

    const card = container.firstElementChild as HTMLElement;
    expect(card.className).toContain("border-[3px]");
    expect(card.className).not.toContain("border-l-4");
    expect(card.style.borderColor).toBe("var(--color-collection-catechism)");
  });

  it("falls back to the accent border for an unknown collection", () => {
    const { container } = render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: null,
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "not-a-collection",
              document_title: "Unknown source",
              author: null,
              reference: null,
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: null,
              chapter_key: null,
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={vi.fn()}
        showToast={vi.fn()}
      />,
    );

    expect((container.firstElementChild as HTMLElement).style.borderColor).toBe("var(--color-brand-accent)");
  });

  it("keeps the inline editor actions responsive on narrow screens", async () => {
    const { container } = render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: null,
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "catechism",
              document_title: "Catechism of the Catholic Church",
              author: null,
              reference: "CCC §1000",
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: "ccc-1000",
              chapter_key: "ccc-1000-1099",
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={vi.fn()}
        showToast={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Add a note" }));
    const saveButton = screen.getByRole("button", { name: "Save note" });
    expect(saveButton.parentElement?.className).toContain("justify-end");
    expect(saveButton.parentElement?.parentElement?.className).toContain("flex-col");
    expect(saveButton.parentElement?.parentElement?.className).toContain("sm:flex-row");
    expect(container.firstElementChild?.className).toContain("overflow-hidden");
  });

  it("keeps the editor and draft available when saving fails", async () => {
    mocks.updateBookmarkNote.mockRejectedValue(new Error("failed"));
    const onNoteUpdated = vi.fn();
    const showToast = vi.fn();
    render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: null,
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "catechism",
              document_title: "Catechism of the Catholic Church",
              author: null,
              reference: "CCC §1000",
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: "ccc-1000",
              chapter_key: "ccc-1000-1099",
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={onNoteUpdated}
        showToast={showToast}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Add a note" }));
    const editor = screen.getByRole("textbox", { name: "Your note" });
    await userEvent.type(editor, "Do not lose this draft");
    await userEvent.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() => expect(showToast).toHaveBeenCalledWith("Couldn't save note. Try again.", "error"));
    expect(onNoteUpdated).not.toHaveBeenCalled();
    expect((screen.getByRole("textbox", { name: "Your note" }) as HTMLTextAreaElement).value).toBe("Do not lose this draft");
  });

  it("removes an existing note when an edited draft contains only whitespace", async () => {
    mocks.updateBookmarkNote.mockResolvedValue({});
    const onNoteUpdated = vi.fn();
    const showToast = vi.fn();
    render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1",
          chunk_id: "chunk-1",
          note: "Remove this note",
          created_at: "2026-08-08T00:00:00Z",
          chunk: {
            content: "A saved passage",
            source: {
              collection: "catechism",
              document_title: "Catechism of the Catholic Church",
              author: null,
              reference: "CCC §1000",
              document_id: "11111111-1111-4111-8111-111111111111",
              anchor: "ccc-1000",
              chapter_key: "ccc-1000-1099",
            },
          },
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={onNoteUpdated}
        showToast={showToast}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const editor = screen.getByRole("textbox", { name: "Your note" });
    await userEvent.clear(editor);
    await userEvent.type(editor, "   ");
    await userEvent.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() => expect(mocks.updateBookmarkNote).toHaveBeenCalledWith("token", "bookmark-1", null));
    expect(onNoteUpdated).toHaveBeenCalledWith("bookmark-1", null);
    expect(showToast).toHaveBeenCalledWith("Note removed");
  });
});

describe("BookmarkCard open in context", () => {
  const bookmark = {
    id: "bookmark-1",
    chunk_id: "chunk-1",
    note: null,
    created_at: "2026-08-08T00:00:00Z",
    chunk: {
      content: "A saved passage",
      source: {
        collection: "catechism",
        document_title: "Catechism of the Catholic Church",
        author: null,
        reference: "CCC §1000",
        document_id: "11111111-1111-4111-8111-111111111111",
        anchor: "ccc-1000",
        chapter_key: "ccc-1000-1099",
      },
    },
  };
  const renderCard = () => render(
    <BookmarkCard bookmark={bookmark} token="token" onRemove={vi.fn().mockResolvedValue(undefined)} onNoteUpdated={vi.fn()} showToast={vi.fn()} />,
  );

  it("links to the reader with a stable href and marks a same-tab return", async () => {
    const { rerender } = renderCard();
    const link = screen.getByRole("link", { name: "Open passage in context" }) as HTMLAnchorElement;
    const href = link.getAttribute("href")!;
    expect(href).toMatch(/^\/reader\/11111111-1111-4111-8111-111111111111\?from=saved&returnKey=[0-9a-f-]{36}&anchor=ccc-1000$/);
    rerender(<BookmarkCard bookmark={bookmark} token="token" onRemove={vi.fn().mockResolvedValue(undefined)} onNoteUpdated={vi.fn()} showToast={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Open passage in context" }).getAttribute("href")).toBe(href);
    expect(link.dataset.prefetch).toBe("false");

    const key = new URL(link.href).searchParams.get("returnKey");
    await userEvent.click(link);
    expect(navigations).toEqual([href]);
    expect(hasReaderReturnMarker(key, "saved")).toBe(true);
    expect(trackDocumentOpened).toHaveBeenCalledWith({ documentId: bookmark.chunk.source.document_id, collection: "catechism", source: "saved" });
  });

  it("leaves a cmd-click to the browser without a return marker", () => {
    renderCard();
    const link = screen.getByRole("link", { name: "Open passage in context" }) as HTMLAnchorElement;
    const event = new MouseEvent("click", { bubbles: true, cancelable: true, metaKey: true });
    link.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(navigations).toEqual([]);
    expect(hasReaderReturnMarker(new URL(link.href).searchParams.get("returnKey"), "saved")).toBe(false);
  });
});


describe("BookmarkCard excerpt-only documents (issue #265)", () => {
  it("links to the source instead of the reader", () => {
    const bookmark = {
      id: "bookmark-1", chunk_id: "chunk-1", note: null, created_at: "2026-10-16T00:00:00Z",
      chunk: {
        content: "A saved passage",
        source: {
          collection: "catechism", document_title: "Catechism of the Catholic Church", author: null,
          reference: "CCC §1000", document_id: "11111111-1111-4111-8111-111111111111",
          anchor: "ccc-1000", chapter_key: "ccc-1000-1099",
          reader_access: "excerpt" as const, source_url: "https://www.vatican.va/archive/ENG0015/_INDEX.HTM",
          source_credit: "Excerpts from the English translation of the Catechism of the Catholic Church",
        },
      },
    };
    render(<BookmarkCard bookmark={bookmark} token="token" onRemove={vi.fn().mockResolvedValue(undefined)} onNoteUpdated={vi.fn()} showToast={vi.fn()} />);

    expect(screen.queryByRole("link", { name: "Open passage in context" })).toBeNull();
    const link = screen.getByRole("link", { name: /Read the full text at the source/ });
    expect(link.getAttribute("href")).toBe("https://www.vatican.va/archive/ENG0015/_INDEX.HTM");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(screen.getByText(/Excerpts from the English translation of the Catechism/)).toBeTruthy();
  });
});

describe("BookmarkCard footnotes (issue #279)", () => {
  const CONTENT = "The death penalty is inadmissible.";
  const CREDIT = "Excerpts from the English translation of the Catechism of the Catholic Church";

  function renderCatechism(footnotes: unknown) {
    const bookmark = {
      id: "bookmark-1", chunk_id: "chunk-1", note: null, created_at: "2026-10-28T00:00:00Z",
      chunk: {
        content: CONTENT,
        footnotes: footnotes as never,
        source: {
          collection: "catechism", document_title: "Catechism of the Catholic Church", author: null,
          reference: "CCC 2267", document_id: "11111111-1111-4111-8111-111111111111",
          anchor: "ccc/2267", chapter_key: null,
          reader_access: "excerpt" as const,
          source_url: "https://www.usccb.org/sites/default/files/flipbooks/catechism/index.html",
          source_credit: CREDIT,
        },
      },
    };
    render(<BookmarkCard bookmark={bookmark} token="token" onRemove={vi.fn().mockResolvedValue(undefined)} onNoteUpdated={vi.fn()} showToast={vi.fn()} />);
  }

  it("puts each marker at its offset and lists the notes", () => {
    renderCatechism([{ n: 68, text: "Francis, Address.", at: CONTENT.length }]);

    const passage = screen.getByText(/death penalty/).closest("p")!;
    expect(passage.querySelector("sup")?.textContent).toBe("68");
    expect(screen.getByText("68. Francis, Address.")).toBeTruthy();
  });

  it("ignores a note whose offset is outside the passage", () => {
    renderCatechism([{ n: 70, text: "Nowhere.", at: -2 }]);

    expect(screen.getByText(CONTENT).querySelector("sup")).toBeNull();
    expect(screen.queryByText("70. Nowhere.")).toBeNull();
  });

  it("copies the text, then its notes, then the credit", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderCatechism([{ n: 68, text: "Francis, Address.", at: CONTENT.length }]);
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));

    const copied = writeText.mock.calls[0][0] as string;
    expect(copied.startsWith(`${CONTENT}⁶⁸ — CCC 2267`)).toBe(true);
    const notes = copied.indexOf("Notes:\n68. Francis, Address.");
    expect(notes).toBeGreaterThan(0);
    expect(copied.endsWith(CREDIT)).toBe(true);
  });
});

describe("BookmarkCard corpus cleanup fields (2.4b)", () => {
  const source = {
    collection: "church-fathers",
    document_title: "Hortatory Address to the Greeks",
    author: "Pseudo-Justin",
    reference: "Justin Martyr — Hortatory Address to the Greeks, Chapter I",
    document_id: "11111111-1111-4111-8111-111111111111",
    anchor: "hortatory/1",
    chapter_key: "hortatory/1",
  };
  function renderBookmark(overrides: Record<string, unknown>, chunk: Record<string, unknown> = {}) {
    render(
      <BookmarkCard
        bookmark={{
          id: "bookmark-1", chunk_id: "chunk-1", note: "My thoughts on this.", created_at: "2026-08-08T00:00:00Z",
          chunk: { content: "Wherefore, O Greeks…", source, ...chunk },
          ...overrides,
        }}
        token="token"
        onRemove={vi.fn().mockResolvedValue(undefined)}
        onNoteUpdated={vi.fn()}
        showToast={vi.fn()}
      />,
    );
  }

  it("shows the translation, notes and the credit under the text, the credit last", () => {
    renderBookmark({}, {
      source: { ...source, facts: { translation: "Translated by Marcus Dods", attribution_note: "Not by Justin Martyr.", source_credit: "Sourced via CCEL.org" } },
    });
    const lines = [...screen.getByTestId("passage-facts").querySelectorAll("p")].map((p) => p.textContent);
    expect(lines).toEqual(["Translated by Marcus Dods", "Not by Justin Martyr.", "Sourced via CCEL.org"]);
  });

  it("shows a removed passage's reason without its text, and keeps the note editable", async () => {
    renderBookmark({
      status: "removed",
      chunk: { content: "", source },
      tombstone: {
        entity: "passage", rule: "G", reason_code: "rule-g-editorial",
        public_reason: "This card was written by an editor of the source, not by the document's author.",
        retired_at: "2026-12-01T00:00:00Z", title: "Hortatory Address to the Greeks", author: "Pseudo-Justin",
      },
    });
    expect(screen.getByText("Removed from TheoCorpus")).toBeTruthy();
    expect(screen.getByText(/written by an editor of the source/)).toBeTruthy();
    expect(screen.queryByText("Wherefore, O Greeks…")).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy passage" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Open passage in context" })).toBeNull();
    expect(screen.getByRole("button", { name: "Remove bookmark" })).toBeTruthy();
    expect(screen.getByText("My thoughts on this.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect((screen.getByLabelText("Your note") as HTMLTextAreaElement).value).toBe("My thoughts on this.");
  });

  it("names the corrected author, drops the stale one from the reference, and copies it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    renderBookmark({}, { source: { ...source, facts: { certainty: "pseudonymous", date_display: "3rd century" } } });
    expect(screen.getByText("Pseudo-Justin · 3rd century")).toBeTruthy();
    expect(screen.getByText("pseudonymous")).toBeTruthy();
    expect(screen.getByText("Hortatory Address to the Greeks, Chapter I")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Copy passage" }));
    expect(writeText.mock.calls[0][0]).toContain("Hortatory Address to the Greeks, Chapter I (Pseudo-Justin)");
    expect(writeText.mock.calls[0][0]).not.toContain("Justin Martyr");
  });

  it("names a quoted Father on a Catena bookmark", () => {
    renderBookmark({}, {
      source: { ...source, collection: "medieval", author: "Thomas Aquinas", document_title: "Catena Aurea", reference: "Catena Aurea, Matthew 5", passage_author: "Chrysostom" },
    });
    expect(screen.getByText("Chrysostom, quoted in Thomas Aquinas's Catena Aurea")).toBeTruthy();
  });

  it("shows no attribution line and today's reference without facts", () => {
    renderBookmark({});
    expect(screen.getByText("Justin Martyr — Hortatory Address to the Greeks, Chapter I")).toBeTruthy();
    expect(screen.queryByText(/Pseudo-Justin/)).toBeNull();
  });

  it("marks a moved passage", () => {
    renderBookmark({ status: "moved", redirect: { kind: "renumbered", document_id: source.document_id, chunk_id: "new" } });
    expect(screen.getByText("This passage was renumbered in a corpus update.")).toBeTruthy();
    expect(screen.getByText("Wherefore, O Greeks…")).toBeTruthy();
  });
});
