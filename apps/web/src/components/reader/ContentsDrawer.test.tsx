// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ContentsDrawer } from "./ContentsDrawer";

afterEach(cleanup);

describe("ContentsDrawer", () => {
  it("does not reset focus when its parent supplies a new close callback", async () => {
    const view = render(
      <ContentsDrawer
        open
        toc={[{ chapter_key: "a", chapter_label: "A" }, { chapter_key: "b", chapter_label: "B" }]}
        currentChapterKey="a"
        onJump={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "A" })));
    screen.getByRole("button", { name: "B" }).focus();

    view.rerender(
      <ContentsDrawer
        open
        toc={[{ chapter_key: "a", chapter_label: "A" }, { chapter_key: "b", chapter_label: "B" }]}
        currentChapterKey="a"
        onJump={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "B" }));
  });

  it("includes the backdrop close action in the keyboard focus loop", async () => {
    render(
      <ContentsDrawer
        open
        toc={[{ chapter_key: "a", chapter_label: "A" }, { chapter_key: "b", chapter_label: "B" }]}
        currentChapterKey="a"
        onJump={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "A" })));
    screen.getByRole("button", { name: "B" }).focus();
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Close contents" }));
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "A" }));
  });
});
