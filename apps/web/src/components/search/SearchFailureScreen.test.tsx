// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchFailureScreen } from "./SearchFailureScreen";

afterEach(cleanup);

describe("SearchFailureScreen restore errors", () => {
  it("does not offer a futile retry for a missing saved search", () => {
    render(
      <SearchFailureScreen
        message="Search not found"
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
        message="Unauthorized"
        code="auth_error"
        stage="authentication"
        onRetry={vi.fn()}
      />,
    );

    expect(screen.getByText("Your session needs to be refreshed")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
  });
});
