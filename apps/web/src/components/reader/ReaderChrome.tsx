"use client";

import { BookOpen, ChevronLeft, ChevronRight, Flag, List, Menu, Settings2 } from "lucide-react";
import type { DocumentInfo, TocEntry } from "@/lib/api";
import { useAppContext } from "@/components/layout/AppShell";

export type ReaderFontSize = "small" | "medium" | "large";
export type ReaderSpacing = "compact" | "comfortable" | "relaxed";

interface Props {
  document: DocumentInfo;
  toc: TocEntry[];
  currentChapterKey: string | null;
  onBack: () => void;
  onToggleContents: () => void;
  onJump: (chapterKey: string) => void;
  fontSize: ReaderFontSize;
  spacing: ReaderSpacing;
  onFontSizeChange: (value: ReaderFontSize) => void;
  onSpacingChange: (value: ReaderSpacing) => void;
  onReportContent: () => void;
}

export function ReaderChrome({
  document,
  toc,
  currentChapterKey,
  onBack,
  onToggleContents,
  onJump,
  fontSize,
  spacing,
  onFontSizeChange,
  onSpacingChange,
  onReportContent,
}: Props) {
  const { openMobileNavigation } = useAppContext();
  const currentIndex = toc.findIndex((entry) => entry.chapter_key === currentChapterKey);
  const previous = currentIndex > 0 ? toc[currentIndex - 1] : null;
  const next = currentIndex >= 0 && currentIndex + 1 < toc.length ? toc[currentIndex + 1] : null;

  return (
    <header className="relative z-10 border-b border-brand-surface bg-brand-bg px-2 py-2 sm:px-4">
      <div className="flex min-h-10 items-center gap-1.5">
        <button
          id="reader-app-nav-trigger"
          type="button"
          onClick={() => openMobileNavigation("reader-app-nav-trigger")}
          className="rounded p-2 text-brand-muted hover:bg-brand-surface hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent md:hidden"
          aria-label="Open app navigation"
        >
          <Menu size={19} />
        </button>
        <button
          type="button"
          onClick={onBack}
          className="rounded p-2 text-brand-muted hover:bg-brand-surface hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          aria-label="Back"
        >
          <ChevronLeft size={19} />
        </button>
        <button
          id="reader-contents-trigger"
          type="button"
          onClick={onToggleContents}
          className="flex min-h-10 items-center gap-1.5 rounded px-2 text-sm text-brand-muted hover:bg-brand-surface hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          <List size={17} />
          <span className="max-sm:sr-only">Contents</span>
        </button>

        <div className="min-w-0 flex-1 px-1">
          <p className="truncate text-sm font-medium text-brand-primary">{document.title}</p>
          {currentIndex >= 0 && (
            <p className="truncate text-[11px] text-brand-muted">
              {toc[currentIndex].chapter_label} · {currentIndex + 1} of {toc.length}
            </p>
          )}
        </div>

        <details className="relative">
          <summary
            className="flex h-10 w-10 cursor-pointer list-none items-center justify-center rounded text-brand-muted hover:bg-brand-surface hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            aria-label="Reading settings"
          >
            <Settings2 size={18} />
          </summary>
          <div className="absolute right-0 top-11 z-20 w-64 rounded-md border border-brand-muted/30 bg-brand-surface p-4 shadow-xl">
            <fieldset>
              <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-brand-muted">Text size</legend>
              <div className="grid grid-cols-3 gap-1">
                {(["small", "medium", "large"] as const).map((value) => (
                  <button key={value} type="button" onClick={() => onFontSizeChange(value)} aria-pressed={fontSize === value} className={`rounded px-2 py-2 text-xs capitalize ${fontSize === value ? "bg-brand-accent text-brand-bg" : "bg-brand-bg text-brand-primary"}`}>{value}</button>
                ))}
              </div>
            </fieldset>
            <fieldset className="mt-4">
              <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-brand-muted">Line spacing</legend>
              <div className="grid grid-cols-3 gap-1">
                {(["compact", "comfortable", "relaxed"] as const).map((value) => (
                  <button key={value} type="button" onClick={() => onSpacingChange(value)} aria-pressed={spacing === value} className={`rounded px-1 py-2 text-[11px] capitalize ${spacing === value ? "bg-brand-accent text-brand-bg" : "bg-brand-bg text-brand-primary"}`}>{value}</button>
                ))}
              </div>
            </fieldset>
            <button type="button" onClick={onReportContent} className="mt-4 flex w-full items-center gap-2 border-t border-brand-muted/20 pt-3 text-left text-xs text-brand-muted hover:text-brand-accent">
              <Flag size={14} aria-hidden="true" /> Report a content issue
            </button>
          </div>
        </details>
      </div>

      <div className="mt-1 flex items-center justify-between gap-2 border-t border-brand-surface pt-2">
        <button type="button" disabled={!previous} onClick={() => previous && onJump(previous.chapter_key)} className="flex min-h-9 items-center gap-1 rounded px-2 text-xs text-brand-muted hover:text-brand-primary disabled:invisible">
          <ChevronLeft size={15} /> Previous
        </button>
        <BookOpen size={15} className="text-brand-accent" aria-hidden="true" />
        <button type="button" disabled={!next} onClick={() => next && onJump(next.chapter_key)} className="flex min-h-9 items-center gap-1 rounded px-2 text-xs text-brand-muted hover:text-brand-primary disabled:invisible">
          Next <ChevronRight size={15} />
        </button>
      </div>
    </header>
  );
}
