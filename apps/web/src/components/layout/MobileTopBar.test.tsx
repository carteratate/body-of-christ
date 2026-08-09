// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MobileTopBar } from "./MobileTopBar";

const state = vi.hoisted(() => ({ pathname: "/sources" }));

vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={String(href)} {...props}>{children}</a>
  ),
}));
vi.mock("./AppShell", () => ({ useAppContext: () => ({ token: "token" }) }));
vi.mock("@/lib/analytics", () => ({ trackNavigationSelected: vi.fn() }));

afterEach(cleanup);

describe("MobileTopBar", () => {
  it("keeps the TheoCorpus brand title on every route", () => {
    render(<MobileTopBar isOpen={false} onOpenMenu={vi.fn()} />);

    expect(screen.getByText("TheoCorpus")).toBeTruthy();
    expect(screen.queryByText("Library")).toBeNull();
  });

  it("keeps the shortcut to history scoped to the search page", () => {
    const view = render(<MobileTopBar isOpen={false} onOpenMenu={vi.fn()} />);
    expect(screen.queryByRole("link", { name: "Search history" })).toBeNull();

    state.pathname = "/search";
    view.rerender(<MobileTopBar isOpen={false} onOpenMenu={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Search history" })).toBeTruthy();
    state.pathname = "/sources";
  });
});
