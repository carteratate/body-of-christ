// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { COLLECTION_SCOPES } from "@/lib/collection-scopes";
import { createSearchDraft, transitionSearchDraft, type SearchDraftEvent } from "@/lib/search-draft";
import { CollectionToggles } from "./CollectionToggles";

function Harness({ collections }: { collections: string[] }) {
  const [draft, setDraft] = useState(() => createSearchDraft({
    preferred_translation: "CPDV", default_collections: collections, default_quota: 4, last_standard_quota: 4,
  }));
  return (
    <>
      <CollectionToggles
        activeCollections={draft.collections}
        onToggle={(collection) => setDraft((d) => transitionSearchDraft(d, { type: "collection-toggled", collection }))}
        excluded={draft.excluded}
        onScopeEvent={(event: SearchDraftEvent) => setDraft((d) => transitionSearchDraft(d, event))}
      />
      <output data-testid="scopes">{JSON.stringify(draft.scopes ?? null)}</output>
      <button type="button">Elsewhere</button>
    </>
  );
}

const scopes = () => JSON.parse(screen.getByTestId("scopes").textContent ?? "null");
const cue = (name: string) => {
  // An unselected collection's caret is aria-hidden, so it has no accessible name to query.
  const element = document.querySelector<HTMLButtonElement>(`[aria-label="Filter ${name} by kind and pope"]`);
  if (!element) throw new Error(`no caret for ${name}`);
  return element;
};

describe("genre and issuer filter (5.1a)", () => {
  afterEach(cleanup);

  it("draws the Bible as a plain toggle, with no translation dropdown", () => {
    render(<Harness collections={["bible"]} />);
    expect(screen.getByRole("button", { name: "Bible" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByRole("button", { name: /translation/i })).toBeNull();
  });

  it("offers the caret only on a selected collection that can be narrowed", () => {
    const { unmount } = render(<Harness collections={["bible"]} />);
    expect(cue("Papal documents").getAttribute("tabindex")).toBe("-1");
    expect(cue("Papal documents").getAttribute("aria-hidden")).toBe("true");
    unmount();
    render(<Harness collections={["papal", "bible"]} />);
    expect(cue("Papal documents").getAttribute("tabindex")).toBe("0");
    expect(screen.queryByRole("button", { name: /Filter Bible/ })).toBeNull();
  });

  it("narrows with Only and a tick, and All returns to everything", () => {
    render(<Harness collections={["papal"]} />);
    fireEvent.click(cue("Papal documents"));
    const dialog = screen.getByRole("dialog", { name: "Search within Papal documents" });
    expect(dialog.textContent).toContain("Kind");
    expect(dialog.textContent).toContain("Pope");

    fireEvent.click(screen.getByRole("button", { name: "Only Encyclical" }));
    // The last ticked value says it cannot be unticked.
    expect(screen.getByRole("checkbox", { name: /^Encyclical/ }).getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(screen.getByRole("checkbox", { name: /Apostolic letter/ }));
    expect(screen.getByRole("checkbox", { name: /^Encyclical/ }).hasAttribute("aria-disabled")).toBe(false);
    expect(scopes()).toEqual({ papal: { genres: ["encyclical", "apostolic-letter"] } });

    fireEvent.click(screen.getByRole("button", { name: "Only Leo XIII" }));
    expect(scopes().papal.issuers).toEqual(["pope-leo-xiii"]);

    fireEvent.click(screen.getByRole("button", { name: "All kinds" }));
    fireEvent.click(screen.getByRole("button", { name: "All popes" }));
    expect(scopes()).toBeNull();
  });

  it("choosing a pope narrows the Kind list to his kinds, and the last one shown stays ticked", () => {
    render(<Harness collections={["papal"]} />);
    fireEvent.click(cue("Papal documents"));
    const kinds = () => screen.getAllByRole("checkbox")
      .filter((box) => box.closest('[role="group"]')?.getAttribute("aria-label") === "Kind")
      .map((box) => box.textContent);
    // The three old papal collections' kinds together (5.1b.2), each with its number of
    // documents. The numbers are read from the generated scope list, which grows with the
    // corpus (collection-scopes.test.ts holds it equal to works.json).
    const documents = COLLECTION_SCOPES.papal.documents;
    const count = (genre: string, issuer?: string) => Object.entries(documents[genre] ?? {})
      .filter(([pope]) => issuer === undefined || pope === issuer)
      .reduce((n, [, k]) => n + k, 0);
    expect(kinds()).toEqual([
      ["Encyclical", "encyclical"], ["Apostolic exhortation", "apostolic-exhortation"],
      ["Apostolic letter", "apostolic-letter"], ["Apostolic constitution", "apostolic-constitution"],
      ["Motu proprio", "motu-proprio"], ["Other", "other"],
    ].map(([label, genre]) => `${label}${count(genre)}`));

    fireEvent.click(screen.getByRole("button", { name: "Only Boniface VIII" }));
    expect(kinds()).toEqual(
      [`Apostolic constitution${count("apostolic-constitution", "pope-boniface-viii")}`]);
    const constitution = screen.getByRole("checkbox", { name: /^Apostolic constitution/ });
    expect(constitution.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(constitution);
    expect(scopes()).toEqual({ papal: { issuers: ["pope-boniface-viii"] } });
  });

  it("closes on a press outside and on Escape, not on a press inside", () => {
    render(<Harness collections={["papal"]} />);
    fireEvent.click(cue("Papal documents"));
    fireEvent.pointerDown(screen.getByRole("checkbox", { name: /^Encyclical/ }));
    expect(screen.queryByRole("dialog")).not.toBeNull();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(cue("Papal documents"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("deselecting a narrowed collection closes its panel and drops its filter", () => {
    render(<Harness collections={["papal", "bible"]} />);
    fireEvent.click(cue("Papal documents"));
    fireEvent.click(screen.getByRole("button", { name: "Only Encyclical" }));
    fireEvent.click(screen.getByRole("button", { name: "Papal documents", pressed: true }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(scopes()).toBeNull();
  });
});

describe("genre and issuer filter focus (5.1a)", () => {
  afterEach(cleanup);

  it("moves focus into the panel once it is placed, and back to the caret on close or Escape", () => {
    render(<Harness collections={["papal"]} />);
    fireEvent.click(cue("Papal documents"));
    const first = screen.getByRole("checkbox", { name: /^Encyclical/ });
    expect(screen.getByRole("dialog").style.visibility).toBe("visible");
    expect(document.activeElement).toBe(first);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(document.activeElement).toBe(cue("Papal documents"));

    fireEvent.click(cue("Papal documents"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(cue("Papal documents"));
  });
});

describe("genre and issuer filter while searching and near the top (5.1a)", () => {
  afterEach(cleanup);

  function toggles(locked: boolean) {
    return (
      <CollectionToggles
        activeCollections={["papal"]}
        onToggle={() => {}}
        excluded={{}}
        onScopeEvent={() => {}}
        scopesLocked={locked}
      />
    );
  }

  it("closes the panel and disables the caret while a search runs", () => {
    const { rerender } = render(toggles(false));
    fireEvent.click(cue("Papal documents"));
    expect(screen.queryByRole("dialog")).not.toBeNull();
    rerender(toggles(true));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(cue("Papal documents").disabled).toBe(true);
    rerender(toggles(false));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it.each([
    ["above, from a caret low on the screen", 700, "bottom"],
    ["below, from a caret near the top", 40, "top"],
  ])("opens %s", (_label, caretTop, side) => {
    render(toggles(false));
    const caret = cue("Papal documents");
    caret.getBoundingClientRect = () => ({
      top: caretTop, bottom: caretTop + 24, left: 200, right: 224, width: 24, height: 24, x: 200, y: caretTop,
      toJSON: () => ({}),
    });
    fireEvent.click(caret);
    const panel = screen.getByRole("dialog");
    expect(panel.style[side as "top" | "bottom"]).not.toBe("");
    expect(panel.hasAttribute("data-below")).toBe(side === "top");
  });
});
