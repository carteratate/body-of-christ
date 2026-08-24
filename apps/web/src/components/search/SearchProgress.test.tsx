// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchProgress } from "./SearchProgress";

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ corpusPassages: 1_234 }),
}));

afterEach(cleanup);

describe("SearchProgress", () => {
  it("derives segment modes from each semantic search phase", () => {
    const view = render(<SearchProgress phase={null} collections={["bible"]} />);

    expect(screen.getByText("Preparing…")).toBeTruthy();
    expect(screen.getByText("Searching 1,234 passages across 1 source")).toBeTruthy();
    expect(view.getAllByTestId("progress-segment").map((segment) => segment.dataset.mode))
      .toEqual(["idle", "idle"]);

    view.rerender(<SearchProgress phase="searching" collections={["bible"]} />);
    expect(screen.getByText("Searching the tradition…")).toBeTruthy();
    expect(view.getAllByTestId("progress-segment").map((segment) => segment.dataset.mode))
      .toEqual(["filling", "idle"]);

    view.rerender(<SearchProgress phase="ranking" collections={["bible"]} />);
    expect(screen.getByText("Refining the top matches…")).toBeTruthy();
    expect(view.getAllByTestId("progress-segment").map((segment) => segment.dataset.mode))
      .toEqual(["complete", "filling"]);
  });

  it("marks the next node as waiting when a fill finishes before its phase arrives", () => {
    const view = render(<SearchProgress phase="searching" collections={["bible"]} />);
    const firstFill = view.getAllByTestId("progress-segment")[0].lastElementChild as HTMLElement;

    const transitionEnd = new Event("transitionend", { bubbles: true });
    Object.defineProperty(transitionEnd, "propertyName", { value: "transform" });
    fireEvent(firstFill, transitionEnd);

    expect(screen.getByLabelText("Waiting for ranking")).toBeTruthy();
  });
});
