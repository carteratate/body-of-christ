// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderChrome } from "./ReaderChrome";

const openMobileNavigation = vi.hoisted(() => vi.fn());

vi.mock("@/components/layout/AppShell", () => ({
  useAppContext: () => ({ mobileNavigationOpen: false, openMobileNavigation }),
}));

afterEach(cleanup);

describe("ReaderChrome", () => {
  it("keeps the TheoCorpus brand beside the mobile app-menu trigger", () => {
    render(
      <ReaderChrome
        document={{ id: "doc-1", title: "Catechism", author: null, collection: "catechism", year: null, metadata: {}, chunk_count: 1 }}
        toc={[{ chapter_key: "chapter-1", chapter_label: "Chapter 1" }]}
        currentChapterKey="chapter-1"
        backLabel="Back to Library"
        onBack={vi.fn()}
        onBrowseSections={vi.fn()}
        onJump={vi.fn()}
        fontSize="medium"
        spacing="comfortable"
        onFontSizeChange={vi.fn()}
        onSpacingChange={vi.fn()}
        onReportContent={vi.fn()}
      />,
    );

    const menu = screen.getByRole("button", { name: "Open app navigation" });
    expect(menu.nextElementSibling?.textContent?.trim()).toBe("TheoCorpus");
    expect(menu.getAttribute("aria-controls")).toBe("mobile-nav-drawer");
    expect(menu.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(menu);
    expect(openMobileNavigation).toHaveBeenCalledWith("reader-app-nav-trigger");
  });

  it("uses a visible source-aware overview action", () => {
    const onBrowseSections = vi.fn();
    render(
      <ReaderChrome
        document={{ id: "doc-1", title: "Catechism", author: null, collection: "catechism", year: null, metadata: {}, chunk_count: 1 }}
        toc={[{ chapter_key: "chapter-1", chapter_label: "Chapter 1" }]}
        currentChapterKey="chapter-1"
        backLabel="Back to Library"
        onBack={vi.fn()}
        onBrowseSections={onBrowseSections}
        onJump={vi.fn()}
        fontSize="medium"
        spacing="comfortable"
        onFontSizeChange={vi.fn()}
        onSpacingChange={vi.fn()}
        onReportContent={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Browse Paragraphs" }));
    expect(onBrowseSections).toHaveBeenCalledOnce();
    expect(screen.queryByText("Contents")).toBeNull();
  });

  it("orders the reading title before the explicit back and browse controls", () => {
    render(
      <ReaderChrome
        document={{ id: "doc-1", title: "Catechism of the Catholic Church", author: null, collection: "catechism", year: null, metadata: {}, chunk_count: 1 }}
        toc={[{ chapter_key: "chapter-1", chapter_label: "CCC §§100–199" }]}
        currentChapterKey="chapter-1"
        backLabel="Back to Library"
        onBack={vi.fn()}
        onBrowseSections={vi.fn()}
        onJump={vi.fn()}
        fontSize="medium"
        spacing="comfortable"
        onFontSizeChange={vi.fn()}
        onSpacingChange={vi.fn()}
        onReportContent={vi.fn()}
      />,
    );

    const back = screen.getByRole("button", { name: "Back to Library" });
    const browse = screen.getByRole("button", { name: "Browse Paragraphs" });
    const title = screen.getByText("Catechism of the Catholic Church");
    expect(title.compareDocumentPosition(back) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(back.compareDocumentPosition(browse) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(title.parentElement?.className).toContain("basis-full");
    expect(title.parentElement?.className).toContain("md:basis-auto");
    expect(back.className).toContain("border-brand-accent");
    expect(back.className).toContain("text-brand-accent");
    expect(title.className).toContain("text-brand-accent");
    for (const control of [
      screen.getByRole("button", { name: "Previous" }),
      screen.getByRole("button", { name: "Next" }),
    ]) {
      expect(control?.className).toContain("border-brand-accent");
      expect(control?.className).toContain("text-brand-accent");
      expect(control?.className).toContain("hover:bg-brand-accent");
      expect(control?.className).toContain("hover:text-brand-bg");
    }
    const settings = document.querySelector('[aria-label="Reading settings"]');
    expect(settings?.parentElement?.className).toContain("ml-auto");
    expect(settings?.className).toContain("border-[0.5px]");
    expect(settings?.className).toContain("border-brand-accent");
    expect(settings?.className).toContain("hover:bg-brand-accent");
    expect(settings?.className).toContain("hover:text-brand-bg");
    expect(screen.getByText("CCC §§100–199 · 1 of 1")).toBeTruthy();
  });
});
