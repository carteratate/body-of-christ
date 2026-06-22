"use client";

import { useRouter } from "next/navigation";
import type { DocumentInfo, TocEntry } from "@/lib/api";

interface Props {
  document: DocumentInfo;
  toc: TocEntry[];
  currentChapterKey: string | null;
  onToggleContents: () => void;
  onJump: (chapterKey: string) => void;
}

export function ReaderChrome({ document, toc, currentChapterKey, onToggleContents, onJump }: Props) {
  const router = useRouter();
  return (
    <div className="sticky top-0 z-10 bg-brand-bg border-b border-brand-surface px-4 py-2 flex items-center gap-2">
      <button
        onClick={() => router.back()}
        className="text-brand-muted text-sm hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        aria-label="Back"
      >
        ←
      </button>
      <button
        onClick={onToggleContents}
        className="text-brand-muted text-sm hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
      >
        ☰ Contents
      </button>
      <span className="text-brand-primary text-sm font-medium truncate">{document.title}</span>
      <select
        value={currentChapterKey ?? ""}
        onChange={(e) => onJump(e.target.value)}
        className="ml-auto bg-brand-surface text-brand-primary text-sm rounded px-2 py-1 border border-brand-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        aria-label="Jump to chapter"
      >
        {toc.map((t) => (
          <option key={t.chapter_key} value={t.chapter_key}>{t.chapter_label}</option>
        ))}
      </select>
    </div>
  );
}
