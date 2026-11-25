"use client";

import { ChevronLeft, ChevronRight, Flag, Settings2 } from "lucide-react";
import type { DocumentInfo, ReaderChapter, TocEntry } from "@/lib/api";
import { IntentLink, NavPendingBar } from "@/components/common/NavPending";
import { ReaderMobileStatusHeader } from "./ReaderMobileStatusHeader";

export type ReaderFontSize = "small" | "medium" | "large";
export type ReaderSpacing = "compact" | "comfortable" | "relaxed";

interface Props {
  document: DocumentInfo;
  toc: TocEntry[];
  /** The reader shows its chapter before the contents arrive; until then the
   *  chrome works from the current chapter's own neighbours. */
  tocStatus?: "loading" | "ready" | "error";
  onRetryToc?: () => void;
  currentChapter?: Pick<ReaderChapter, "chapter_label" | "prev_chapter_key" | "next_chapter_key"> | null;
  currentChapterKey: string | null;
  backLabel: string;
  onBack: () => void;
  /** The Back navigation is in flight (it opens a page rather than popping history). */
  backPending?: boolean;
  onBrowseSections: () => void;
  onJump: (chapterKey: string) => void;
  fontSize: ReaderFontSize;
  spacing: ReaderSpacing;
  onFontSizeChange: (value: ReaderFontSize) => void;
  onSpacingChange: (value: ReaderSpacing) => void;
  /** Saves the feedback context; the link itself opens reportHref. */
  onReportContent: () => void;
  reportHref: string;
  showBackGuide?: boolean;
  onDismissBackGuide?: () => void;
}

export function ReaderChrome({
  document,
  toc,
  tocStatus = "ready",
  onRetryToc,
  currentChapter = null,
  currentChapterKey,
  backLabel,
  onBack,
  backPending = false,
  onBrowseSections,
  onJump,
  fontSize,
  spacing,
  onFontSizeChange,
  onSpacingChange,
  onReportContent,
  reportHref,
  showBackGuide = false,
  onDismissBackGuide,
}: Props) {
  // The contents position the chapter when they include it. A chapter they do not
  // list (contents older or newer than the chapter) still has its own neighbours.
  const currentIndex = tocStatus === "ready" ? toc.findIndex((entry) => entry.chapter_key === currentChapterKey) : -1;
  const positioned = currentIndex >= 0;
  const previousKey = positioned
    ? (currentIndex > 0 ? toc[currentIndex - 1].chapter_key : null)
    : currentChapter?.prev_chapter_key ?? null;
  const nextKey = positioned
    ? (currentIndex + 1 < toc.length ? toc[currentIndex + 1].chapter_key : null)
    : currentChapter?.next_chapter_key ?? null;
  // The overview button returns to the document's overview page, so it names the
  // document in every collection (a Bible book is its own document: "Back to Genesis").
  const overviewLabel = `Back to ${document.title}`;

  return (
    <header className="relative z-10 border-b border-brand-surface bg-brand-bg px-2 py-2 sm:px-4">
      <ReaderMobileStatusHeader embedded />

      <div className="mt-1 flex min-h-10 flex-wrap items-center gap-2 md:mt-0 md:flex-nowrap">
        <div className="min-w-0 basis-full px-1 md:max-w-[18rem] md:basis-auto md:shrink">
          <p className="truncate text-sm font-medium text-brand-accent">{document.title}</p>
          {positioned ? (
            <p className="truncate text-[11px] text-brand-muted">
              {toc[currentIndex].chapter_label} · {currentIndex + 1} of {toc.length}
            </p>
          ) : currentChapter && (
            <p className="truncate text-[11px] text-brand-muted" aria-busy={tocStatus === "loading"}>
              {currentChapter.chapter_label}
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
            aria-busy={backPending || undefined}
            className="relative flex min-h-9 items-center gap-1 rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            aria-label={backLabel}
          >
            <ChevronLeft size={16} aria-hidden="true" />
            {backLabel}
            <NavPendingBar pending={backPending} />
          </button>
        </div>

        {/* The overview and settings buttons wrap as one, so settings is never left on
            a line alone. The overview button takes the room left and cuts a long title
            with an ellipsis to fit it; under 9rem the pair moves to a line of its own.
            The full title shows above it. */}
        <div className="flex min-w-0 grow basis-52 items-center gap-2">
          <div className="flex min-w-0 flex-1">
            <button
              type="button"
              onClick={onBrowseSections}
              title={overviewLabel}
              className="flex min-h-9 max-w-full items-center rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              <span className="truncate">{overviewLabel}</span>
            </button>
          </div>

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
              <IntentLink href={reportHref} onClick={onReportContent} className="mt-4 flex w-full items-center gap-2 border-t border-brand-muted/20 pt-3 text-left text-xs text-brand-muted hover:text-brand-accent">
                <Flag size={14} aria-hidden="true" /> Report a content issue
              </IntentLink>
            </div>
          </details>
        </div>
      </div>

      <div className="mt-1 flex items-center justify-between gap-2 border-t border-brand-surface pt-2">
        <button type="button" disabled={!previousKey} onClick={() => previousKey && onJump(previousKey)} className="flex min-h-9 items-center gap-1 rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent disabled:invisible">
          <ChevronLeft size={15} /> Previous
        </button>
        {/* Kept out of the truncated title block so a long chapter label cannot clip it. */}
        {tocStatus === "error" && (
          <button type="button" onClick={onRetryToc} className="min-h-9 min-w-0 px-2 text-center text-xs leading-tight text-brand-muted hover:text-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
            Contents didn&apos;t load. <span className="font-semibold text-brand-accent">Retry</span>
          </button>
        )}
        <button type="button" disabled={!nextKey} onClick={() => nextKey && onJump(nextKey)} className="flex min-h-9 items-center gap-1 rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent disabled:invisible">
          Next <ChevronRight size={15} />
        </button>
      </div>
    </header>
  );
}
