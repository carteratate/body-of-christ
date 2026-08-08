"use client";

import { useEffect, useRef } from "react";

import type { TocEntry } from "@/lib/api";

interface Props {
  open: boolean;
  toc: TocEntry[];
  currentChapterKey: string | null;
  onJump: (chapterKey: string) => void;
  onClose: () => void;
}

export function ContentsDrawer({ open, toc, currentChapterKey, onJump, onClose }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    if (!open) return;
    dialogRef.current?.querySelector<HTMLElement>("button")?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const items = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button:not([disabled])"));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.getElementById("reader-contents-trigger")?.focus();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div ref={dialogRef} className="fixed inset-0 z-20 flex" role="dialog" aria-modal="true" aria-label="Document contents">
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
      <button type="button" className="flex-1 bg-black/40" onClick={onClose} aria-label="Close contents" />
    </div>
  );
}
