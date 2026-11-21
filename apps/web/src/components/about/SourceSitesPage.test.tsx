// @vitest-environment jsdom

// About › Sources (corpus cleanup 4.4).

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceSitesPage } from "./SourceSitesPage";
import { SOURCE_SITES } from "@/lib/source-sites";

vi.mock("next/link", () => import("@/test/next-link-mock"));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/about/sources",
}));

afterEach(cleanup);

describe("SourceSitesPage", () => {
  it("lists every site, what is taken, its basis and its documents", () => {
    render(<SourceSitesPage />);
    const sections = screen.getAllByTestId("source-site");
    expect(sections).toHaveLength(SOURCE_SITES.length);
    for (const [i, site] of SOURCE_SITES.entries()) {
      const section = within(sections[i]);
      const link = section.getByRole("link", { name: new RegExp(site.name.replace(/[()]/g, "\\$&")) });
      expect(link.getAttribute("href")).toBe(site.url);
      expect(link.getAttribute("target")).toBe("_blank");
      expect(section.getByText(site.taken)).toBeTruthy();
      for (const basis of site.basis) expect(section.getByText(basis)).toBeTruthy();
      for (const basis of site.excerpt_bases) {
        expect(section.getByRole("link", { name: new RegExp(basis.statement.slice(0, 30).replace(/[()]/g, "\\$&")) })
          .getAttribute("href")).toBe(basis.url);
      }
      expect(sections[i].querySelectorAll("li")).toHaveLength(site.documents.length);
    }
  });

  it("names the sites the spec lists", () => {
    expect(SOURCE_SITES.map((s) => s.key)).toEqual(expect.arrayContaining(
      ["ccel", "ebible", "vatican", "papalencyclicals", "wikisource", "archive", "usccb"]));
  });

  it("leads back to the guest About page for a guest", () => {
    render(<SourceSitesPage isGuest />);
    expect(screen.getByRole("link", { name: "About" }).getAttribute("href")).toBe("/guest/about");
  });
});
