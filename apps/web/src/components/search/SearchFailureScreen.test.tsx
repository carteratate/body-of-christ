// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchFailureScreen } from "./SearchFailureScreen";

afterEach(cleanup);

describe("SearchFailureScreen restore errors", () => {
  it("does not offer a futile retry for a missing saved search", () => {
    render(
      <SearchFailureScreen
        code="restore_not_found"
        stage="restore"
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("Saved search not found")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry saved search" })).toBeNull();
  });

  it("does not offer restore retry when authentication has expired", () => {
    render(
      <SearchFailureScreen
        code="auth_error"
        stage="authentication"
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("Please sign in again")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
  });

  it("uses plain language for internal search failures", () => {
    render(
      <SearchFailureScreen
        code="server_error"
        stage="retrieval"
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("We couldn't complete this search")).toBeTruthy();
    expect(screen.getByText("Try again. If it keeps happening, report the problem.")).toBeTruthy();
    expect(screen.queryByText(/retrieval/i)).toBeNull();
    expect(screen.queryByText(/relevance decision/i)).toBeNull();
  });
});
