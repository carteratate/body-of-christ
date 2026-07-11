"use client";

import { useEffect, useRef, useState, Suspense, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import {
  getToc,
  getReaderChapter,
  type ReaderChapter,
  type TocEntry,
  type DocumentInfo,
} from "@/lib/api";
import { ReaderChrome } from "./ReaderChrome";
import { ContentsDrawer } from "./ContentsDrawer";
import { ChapterSection } from "./ChapterSection";

function Inner({ docId }: { docId: string }) {
  const { token } = useAppContext();
  const router = useRouter();
  const params = useSearchParams();
  const initialAnchor = params.get("anchor");
  const initialChapter = params.get("chapter");

  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [toc, setToc] = useState<TocEntry[]>([]);
  const [chapters, setChapters] = useState<ReaderChapter[]>([]); // ordered buffer
  const [currentKey, setCurrentKey] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string | null>(initialAnchor);
  const [contentsOpen, setContentsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chapterLoading, setChapterLoading] = useState<string | null>(null);
  const [chapterError, setChapterError] = useState<{ key: string; mode: "append" | "replace" } | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Chapter keys already requested for append — a synchronous guard against the
  // infinite-scroll race where many scroll events fire before state settles and
  // each re-appends the same next chapter. Refs update immediately, unlike state.
  const requestedRef = useRef<Set<string>>(new Set());

  // Initial load: TOC + first/target chapter.
  useEffect(() => {
    if (!token) return;
    let alive = true;
    (async () => {
      try {
        setLoading(true);
        const [tocResp, chapter] = await Promise.all([
          getToc(token, docId),
          getReaderChapter(token, docId, {
            anchor: initialAnchor ?? undefined,
            chapter: initialChapter ?? undefined,
          }),
        ]);
        if (!alive) return;
        setDoc(tocResp.document);
        setToc(tocResp.chapters);
        setChapters([chapter]);
        setCurrentKey(chapter.chapter_key);
        requestedRef.current = new Set([chapter.chapter_key]);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, docId]);

  // Scroll the highlighted passage into view after first render.
  useEffect(() => {
    if (highlight && chapters.length === 1) {
      document
        .getElementById(`anchor-${highlight}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [chapters, highlight]);

  const loadChapter = useCallback(async (key: string, mode: "append" | "replace") => {
    if (!token) return;
    // Synchronous dedupe: skip if this append was already requested this session.
    if (mode === "append" && requestedRef.current.has(key)) return;
    requestedRef.current.add(key);
    setChapterLoading(key);
    setChapterError(null);
    try {
      const chapter = await getReaderChapter(token, docId, { chapter: key });
      setChapters((prev) => {
        if (mode === "replace") return [chapter];
        if (prev.some((c) => c.chapter_key === key)) return prev;
        return [...prev, chapter];
      });
      if (mode === "replace") setCurrentKey(key);
    } catch {
      requestedRef.current.delete(key);
      setChapterError({ key, mode });
    } finally {
      setChapterLoading(null);
    }
  }, [token, docId]);

  const jump = useCallback((key: string) => {
    requestedRef.current = new Set([key]); // reset append history for the new anchor
    setCurrentKey(key);
    setHighlight(null);
    loadChapter(key, "replace");
    scrollRef.current?.scrollTo({ top: 0 });
  }, [loadChapter]);

  // Infinite scroll + current-chapter tracking.
  function onScroll(e: React.UIEvent<HTMLDivElement>) {
    const el = e.currentTarget;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 600) {
      const last = chapters[chapters.length - 1];
      if (last?.next_chapter_key && !chapters.some((c) => c.chapter_key === last.next_chapter_key)) {
        loadChapter(last.next_chapter_key, "append");
      }
    }
    // Track which chapter heading is at/above the top of the viewport.
    const contTop = el.getBoundingClientRect().top;
    let cur = currentKey;
    el.querySelectorAll("section[data-chapter-key]").forEach((s) => {
      if (s.getBoundingClientRect().top - contTop <= 80) {
        cur = s.getAttribute("data-chapter-key");
      }
    });
    if (cur && cur !== currentKey) setCurrentKey(cur);
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-brand-bg gap-4">
        <p className="text-brand-muted text-sm">This document couldn&apos;t be loaded.</p>
        <button onClick={() => router.back()} className="text-brand-accent text-sm hover:underline">← Back</button>
      </div>
    );
  }
  if (loading && !doc) {
    return (
      <div className="flex flex-col h-full bg-brand-bg px-6 pt-8 space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="animate-pulse bg-brand-surface rounded h-4" style={{ width: `${70 + (i % 3) * 10}%` }} />
        ))}
      </div>
    );
  }
  if (!doc) return null;

  return (
    <div className="flex flex-col h-full bg-brand-bg">
      <ReaderChrome
        document={doc}
        toc={toc}
        currentChapterKey={currentKey}
        onToggleContents={() => setContentsOpen((v) => !v)}
        onJump={jump}
      />
      <ContentsDrawer
        open={contentsOpen}
        toc={toc}
        currentChapterKey={currentKey}
        onJump={jump}
        onClose={() => setContentsOpen(false)}
      />
      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
        {chapters.map((ch) => (
          <ChapterSection key={ch.chapter_key} chapter={ch} highlightAnchor={highlight} />
        ))}
        {chapterLoading && (
          <div className="px-6 py-8 space-y-3 animate-pulse" aria-label="Loading chapter">
            <div className="h-4 w-2/3 rounded bg-brand-surface" />
            <div className="h-4 w-full rounded bg-brand-surface" />
            <div className="h-4 w-5/6 rounded bg-brand-surface" />
          </div>
        )}
        {chapterError && (
          <div className="px-6 py-6 text-center">
            <p className="text-sm text-brand-muted mb-2">Chapter couldn&apos;t be loaded.</p>
            <button className="text-sm text-brand-accent hover:underline" onClick={() => loadChapter(chapterError.key, chapterError.mode)}>Retry</button>
          </div>
        )}
      </div>
    </div>
  );
}

export function DocumentReader({ docId }: { docId: string }) {
  return (
    <Suspense>
      <Inner docId={docId} />
    </Suspense>
  );
}
