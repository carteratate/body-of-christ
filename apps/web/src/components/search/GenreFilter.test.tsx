// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

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
        translation={draft.translation}
        onTranslationChange={() => {}}
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

  it("offers the caret only on a selected collection that can be narrowed", () => {
    render(<Harness collections={["encyclicals", "bible"]} />);
    expect(cue("Encyclicals").getAttribute("tabindex")).toBe("0");
    expect(cue("Papal Documents").getAttribute("tabindex")).toBe("-1");
    expect(cue("Papal Documents").getAttribute("aria-hidden")).toBe("true");
    expect(screen.queryByRole("button", { name: /Filter Bible/ })).toBeNull();
  });

  it("narrows with Only and a tick, and All returns to everything", () => {
    render(<Harness collections={["encyclicals"]} />);
    fireEvent.click(cue("Encyclicals"));
    const dialog = screen.getByRole("dialog", { name: "Search within Encyclicals" });
    expect(dialog.textContent).toContain("Kind");
    expect(dialog.textContent).toContain("Pope");

    fireEvent.click(screen.getByRole("button", { name: "Only Encyclical" }));
    // The last ticked value says it cannot be unticked.
    expect(screen.getByRole("checkbox", { name: /^Encyclical/ }).getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(screen.getByRole("checkbox", { name: /Apostolic letter/ }));
    expect(screen.getByRole("checkbox", { name: /^Encyclical/ }).hasAttribute("aria-disabled")).toBe(false);
    expect(scopes()).toEqual({ encyclicals: { genres: ["encyclical", "apostolic-letter"] } });

    fireEvent.click(screen.getByRole("button", { name: "Only Leo XIII" }));
    expect(scopes().encyclicals.issuers).toEqual(["pope-leo-xiii"]);

    fireEvent.click(screen.getByRole("button", { name: "All kinds" }));
    fireEvent.click(screen.getByRole("button", { name: "All popes" }));
    expect(scopes()).toBeNull();
  });

  it("has no Kind list for a collection with one genre", () => {
    render(<Harness collections={["apostolic-exhortations"]} />);
    fireEvent.click(cue("Apostolic Exhortations"));
    expect(screen.getByRole("dialog").textContent).not.toContain("Kind");
  });

  it("closes on a press outside and on Escape, not on a press inside", () => {
    render(<Harness collections={["encyclicals"]} />);
    fireEvent.click(cue("Encyclicals"));
    fireEvent.pointerDown(screen.getByRole("checkbox", { name: /^Encyclical/ }));
    expect(screen.queryByRole("dialog")).not.toBeNull();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(cue("Encyclicals"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("deselecting a narrowed collection closes its panel and drops its filter", () => {
    render(<Harness collections={["encyclicals", "bible"]} />);
    fireEvent.click(cue("Encyclicals"));
    fireEvent.click(screen.getByRole("button", { name: "Only Encyclical" }));
    fireEvent.click(screen.getByRole("button", { name: "Encyclicals", pressed: true }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(scopes()).toBeNull();
  });
});

describe("genre and issuer filter focus (5.1a)", () => {
  afterEach(cleanup);

  it("moves focus into the panel once it is placed, and back to the caret on close or Escape", () => {
    render(<Harness collections={["encyclicals"]} />);
    fireEvent.click(cue("Encyclicals"));
    const first = screen.getByRole("checkbox", { name: /^Encyclical/ });
    expect(screen.getByRole("dialog").style.visibility).toBe("visible");
    expect(document.activeElement).toBe(first);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(document.activeElement).toBe(cue("Encyclicals"));

    fireEvent.click(cue("Encyclicals"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(cue("Encyclicals"));
  });
});

describe("genre and issuer filter while searching and near the top (5.1a)", () => {
  afterEach(cleanup);

  function toggles(locked: boolean) {
    return (
      <CollectionToggles
        activeCollections={["encyclicals"]}
        onToggle={() => {}}
        translation="CPDV"
        onTranslationChange={() => {}}
        excluded={{}}
        onScopeEvent={() => {}}
        scopesLocked={locked}
      />
    );
  }

  it("closes the panel and disables the caret while a search runs", () => {
    const { rerender } = render(toggles(false));
    fireEvent.click(cue("Encyclicals"));
    expect(screen.queryByRole("dialog")).not.toBeNull();
    rerender(toggles(true));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(cue("Encyclicals").disabled).toBe(true);
    rerender(toggles(false));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it.each([
    ["above, from a caret low on the screen", 700, "bottom"],
    ["below, from a caret near the top", 40, "top"],
  ])("opens %s", (_label, caretTop, side) => {
    render(toggles(false));
    const caret = cue("Encyclicals");
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
