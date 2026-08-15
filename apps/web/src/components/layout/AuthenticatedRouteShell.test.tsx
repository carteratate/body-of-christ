// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthenticatedRouteShell } from "./AuthenticatedRouteShell";

const state = vi.hoisted(() => ({ pathname: "/search", mounts: 0 }));

vi.mock("next/navigation", () => ({
  usePathname: () => state.pathname,
}));

vi.mock("./AppShell", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  return {
    AppShell: ({ children }: { children: React.ReactNode }) => {
      React.useEffect(() => {
        state.mounts += 1;
      }, []);
      return <div data-testid="authenticated-shell">{children}</div>;
    },
  };
});

vi.mock("./GuestShell", () => ({
  GuestShell: ({ children }: { children: React.ReactNode }) => <div data-testid="guest-shell">{children}</div>,
}));

beforeEach(() => {
  state.pathname = "/search";
  state.mounts = 0;
});

afterEach(cleanup);

describe("AuthenticatedRouteShell", () => {
  it("keeps one AppShell mounted across authenticated navigation", () => {
    const view = render(<AuthenticatedRouteShell><div>Search page</div></AuthenticatedRouteShell>);
    expect(screen.getByTestId("authenticated-shell")).toBeTruthy();
    expect(state.mounts).toBe(1);

    state.pathname = "/sources";
    view.rerender(<AuthenticatedRouteShell><div>Library page</div></AuthenticatedRouteShell>);

    expect(screen.getByText("Library page")).toBeTruthy();
    expect(state.mounts).toBe(1);
  });

  it("wraps guest routes separately and leaves public routes unwrapped", () => {
    state.pathname = "/search/guest";
    const view = render(<AuthenticatedRouteShell><div>Guest page</div></AuthenticatedRouteShell>);
    expect(screen.queryByTestId("authenticated-shell")).toBeNull();
    expect(screen.getByTestId("guest-shell")).toBeTruthy();

    state.pathname = "/login";
    view.rerender(<AuthenticatedRouteShell><div>Login page</div></AuthenticatedRouteShell>);
    expect(screen.queryByTestId("authenticated-shell")).toBeNull();
    expect(screen.queryByTestId("guest-shell")).toBeNull();
  });

  it("wraps chat and near-guest authenticated paths", () => {
    state.pathname = "/chat";
    const view = render(<AuthenticatedRouteShell><div>Chat</div></AuthenticatedRouteShell>);
    expect(screen.getByTestId("authenticated-shell")).toBeTruthy();

    state.pathname = "/search/guestbook";
    view.rerender(<AuthenticatedRouteShell><div>Near guest</div></AuthenticatedRouteShell>);
    expect(screen.getByTestId("authenticated-shell")).toBeTruthy();
  });
});
