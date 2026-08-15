"use client";

import { ChevronLeft, ChevronRight, Flag, Settings2 } from "lucide-react";
import type { DocumentInfo, TocEntry } from "@/lib/api";
import { ReaderMobileStatusHeader } from "./ReaderMobileStatusHeader";

export type ReaderFontSize = "small" | "medium" | "large";
export type ReaderSpacing = "compact" | "comfortable" | "relaxed";

interface Props {
  document: DocumentInfo;
  toc: TocEntry[];
  currentChapterKey: string | null;
  backLabel: string;
  onBack: () => void;
  onBrowseSections: () => void;
  onJump: (chapterKey: string) => void;
  fontSize: ReaderFontSize;
  spacing: ReaderSpacing;
  onFontSizeChange: (value: ReaderFontSize) => void;
  onSpacingChange: (value: ReaderSpacing) => void;
  onReportContent: () => void;
  showBackGuide?: boolean;
  onDismissBackGuide?: () => void;
}

export function ReaderChrome({
  document,
  toc,
  currentChapterKey,
  backLabel,
  onBack,
  onBrowseSections,
  onJump,
  fontSize,
  spacing,
  onFontSizeChange,
  onSpacingChange,
  onReportContent,
  showBackGuide = false,
  onDismissBackGuide,
}: Props) {
  const currentIndex = toc.findIndex((entry) => entry.chapter_key === currentChapterKey);
  const previous = currentIndex > 0 ? toc[currentIndex - 1] : null;
  const next = currentIndex >= 0 && currentIndex + 1 < toc.length ? toc[currentIndex + 1] : null;
  const browseLabel = document.collection === "bible"
    ? "Browse Chapters"
    : document.collection === "catechism"
      ? "Browse Paragraphs"
      : document.collection === "summa"
        ? "Browse Articles"
        : document.collection === "canon-law"
          ? "Browse Books & Sections"
          : "Browse Sections";

  return (
    <header className="relative z-10 border-b border-brand-surface bg-brand-bg px-2 py-2 sm:px-4">
      <ReaderMobileStatusHeader embedded />

      <div className="mt-1 flex min-h-10 flex-wrap items-center gap-2 md:mt-0 md:flex-nowrap">
        <div className="min-w-0 basis-full px-1 md:max-w-[18rem] md:basis-auto md:shrink">
          <p className="truncate text-sm font-medium text-brand-accent">{document.title}</p>
          {currentIndex >= 0 && (
            <p className="truncate text-[11px] text-brand-muted">
              {toc[currentIndex].chapter_label} · {currentIndex + 1} of {toc.length}
            </p>
          )}
        </div>

        <div className="relative shrink-0">
          {showBackGuide && (
            <div role="status" className="absolute left-0 top-[calc(100%+10px)] z-30 w-60 rounded-lg border border-brand-accent/40 bg-brand-surface px-3 py-2 text-xs leading-relaxed text-brand-primary shadow-xl before:absolute before:-top-1.5 before:left-6 before:h-3 before:w-3 before:rotate-45 before:border-l before:border-t before:border-brand-accent/40 before:bg-brand-surface">
              <button type="button" onClick={onDismissBackGuide} aria-label="Dismiss return guidance" className="absolute right-1.5 top-1 text-brand-muted hover:text-brand-primary">×</button>
              <span className="block pr-3">Return to your search to explore the other passages TheoCorpus found.</span>
            </div>
          )}
          <button
            type="button"
            onClick={onBack}
            className="flex min-h-9 items-center gap-1 rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            aria-label={backLabel}
          >
            <ChevronLeft size={16} aria-hidden="true" />
            {backLabel}
          </button>
        </div>

        <button
          type="button"
          onClick={onBrowseSections}
          className="min-h-9 shrink-0 rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          {browseLabel}
        </button>

        <details className="relative ml-auto">
          <summary
            className="flex h-10 w-10 cursor-pointer list-none items-center justify-center rounded-md border-[0.5px] border-brand-accent text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
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
        <button type="button" disabled={!previous} onClick={() => previous && onJump(previous.chapter_key)} className="flex min-h-9 items-center gap-1 rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent disabled:invisible">
          <ChevronLeft size={15} /> Previous
        </button>
        <button type="button" disabled={!next} onClick={() => next && onJump(next.chapter_key)} className="flex min-h-9 items-center gap-1 rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent disabled:invisible">
          Next <ChevronRight size={15} />
        </button>
      </div>
    </header>
  );
}
