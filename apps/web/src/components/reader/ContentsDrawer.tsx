"use client";

import type { TocEntry } from "@/lib/api";

interface Props {
  open: boolean;
  toc: TocEntry[];
  currentChapterKey: string | null;
  onJump: (chapterKey: string) => void;
  onClose: () => void;
}

export function ContentsDrawer({ open, toc, currentChapterKey, onJump, onClose }: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-20 flex">
      <div className="w-72 max-w-[80vw] bg-brand-surface h-full overflow-y-auto p-4">
        <p className="text-brand-muted text-xs uppercase tracking-wide mb-3">Contents</p>
        <ul className="space-y-1">
          {toc.map((t) => (
            <li key={t.chapter_key}>
              <button
                onClick={() => { onJump(t.chapter_key); onClose(); }}
                className={`text-sm text-left w-full px-2 py-1 rounded hover:bg-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${
                  t.chapter_key === currentChapterKey ? "text-brand-accent" : "text-brand-primary"
                }`}
              >
                {t.chapter_label}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex-1 bg-black/40" onClick={onClose} />
    </div>
  );
}
