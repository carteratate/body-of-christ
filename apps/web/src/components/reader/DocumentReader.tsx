"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import {
  getReadingProgress,
  getReaderChapter,
  getToc,
  putReadingProgress,
  type DocumentInfo,
  type ReaderChapter,
  type TocEntry,
} from "@/lib/api";
import { ChapterSection } from "./ChapterSection";
import { ReaderChrome, type ReaderFontSize, type ReaderSpacing } from "./ReaderChrome";
import { saveFeedbackContext } from "@/lib/feedbackContext";
import { ReaderChapterSkeleton, ReaderOverviewSkeleton, ReaderPageSkeleton } from "@/components/common/PageSkeletons";
import { DocumentOverview } from "./DocumentOverview";
import { consumeReaderReturnKey, isReaderReturnKey, type ReaderOrigin } from "@/lib/readerNavigation";
import { getGuestSessionToken } from "@/lib/trial";
import { ReaderMobileStatusHeader } from "./ReaderMobileStatusHeader";
import { useGuestGate } from "@/components/layout/guestGate";

const ORIGINS = new Set(["search", "saved", "library", "history"]);

interface ProgressWriter {
  token: string;
  docId: string;
  inFlight: boolean;
  queued: string | null;
  failed: string | null;
}

function Inner({ docId, isGuest = false }: { docId: string; isGuest?: boolean }) {
  const { token } = useAppContext();
  const guestGate = useGuestGate();
  const [guestToken, setGuestToken] = useState("");
  const router = useRouter();
  const params = useSearchParams();
  const initialAnchor = params.get("anchor");
  const initialChapter = params.get("chapter");
  const originParam = params.get("from");
  const origin = (originParam && ORIGINS.has(originParam) ? originParam : "library") as ReaderOrigin;
  const returnKey = params.get("returnKey");
  const [showBackGuide, setShowBackGuide] = useState(isGuest && params.get("guideBack") === "1");
  const backLabel = origin === "saved"
    ? "Back to Saved Passages"
    : origin === "history"
      ? "Back to Search History"
      : origin === "search"
        ? "Back to Search"
        : "Back to Library";

  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [toc, setToc] = useState<TocEntry[]>([]);
  const [chapters, setChapters] = useState<ReaderChapter[]>([]);
  const [currentKey, setCurrentKey] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string | null>(initialAnchor);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialRetryKey, setInitialRetryKey] = useState(0);
  const [chapterLoading, setChapterLoading] = useState<string | null>(null);
  const [chapterError, setChapterError] = useState<{ key: string; mode: "append" | "replace" } | null>(null);
  const [progressError, setProgressError] = useState(false);
  const [initialResolved, setInitialResolved] = useState(false);
  const [resolvedDocId, setResolvedDocId] = useState<string | null>(null);
  const [fontSize, setFontSize] = useState<ReaderFontSize>("medium");
  const [spacing, setSpacing] = useState<ReaderSpacing>("comfortable");
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const requestedRef = useRef<Set<string>>(new Set());
  const pendingAppendsRef = useRef<Map<string, number>>(new Map());
  const chapterRequestRef = useRef(0);
  const replacePendingRef = useRef(false);
  const progressWriterRef = useRef<ProgressWriter | null>(null);

  useEffect(() => { if (isGuest) queueMicrotask(() => setGuestToken(getGuestSessionToken())); }, [isGuest]);

  useEffect(() => {
    try {
      const storedFont = localStorage.getItem("theocorpus-reader-font");
      const storedSpacing = localStorage.getItem("theocorpus-reader-spacing");
      if (storedFont === "small" || storedFont === "medium" || storedFont === "large") setFontSize(storedFont);
      if (storedSpacing === "compact" || storedSpacing === "comfortable" || storedSpacing === "relaxed") setSpacing(storedSpacing);
    } catch {}
  }, []);

  function changeFontSize(value: ReaderFontSize) {
    setFontSize(value);
    try { localStorage.setItem("theocorpus-reader-font", value); } catch {}
  }

  function changeSpacing(value: ReaderSpacing) {
    setSpacing(value);
    try { localStorage.setItem("theocorpus-reader-spacing", value); } catch {}
  }

  useEffect(() => {
    if (!token && !guestToken) return;
    const controller = new AbortController();
    let alive = true;
    chapterRequestRef.current += 1;
    replacePendingRef.current = false;
    setInitialResolved(false);
    setResolvedDocId(null);
    setError(null);
    setLoading(true);
    setDoc(null);
    setToc([]);
    setChapters([]);
    setCurrentKey(null);
    pendingAppendsRef.current.clear();
    setHighlight(initialAnchor);
    (async () => {
      try {
        const tocResponse = await getToc(token ?? "", docId, controller.signal, guestToken || undefined);
        const options: { anchor?: string; chapter?: string; signal?: AbortSignal } = { signal: controller.signal };
        if (initialAnchor) {
          options.anchor = initialAnchor;
        } else if (initialChapter) {
          options.chapter = initialChapter;
        } else {
          try {
            const progress = isGuest ? null : await getReadingProgress(token!, docId, controller.signal);
            if (progress) options.chapter = progress.chapter_key;
          } catch {
            // Progress is optional; the document still opens at its first chapter.
          }
        }
        let chapter: ReaderChapter;
        try {
          chapter = await getReaderChapter(token ?? "", docId, { ...options, guestToken: guestToken || undefined });
        } catch {
          if (!options.chapter || initialChapter) throw new Error("Failed to load requested chapter");
          chapter = await getReaderChapter(token ?? "", docId, { signal: controller.signal, guestToken: guestToken || undefined });
        }
        if (!alive) return;
        setDoc(tocResponse.document);
        setToc(tocResponse.chapters);
        setChapters([chapter]);
        setCurrentKey(chapter.chapter_key);
        requestedRef.current = new Set([chapter.chapter_key]);
        setInitialResolved(true);
        setResolvedDocId(docId);
      } catch (caught) {
        if (alive && (caught as DOMException).name !== "AbortError") setError("Failed to load");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
      controller.abort();
      chapterRequestRef.current += 1;
      replacePendingRef.current = false;
    };
  }, [docId, guestToken, initialAnchor, initialChapter, initialRetryKey, isGuest, token]);

  useEffect(() => {
    progressWriterRef.current = token && !isGuest
      ? { token, docId, inFlight: false, queued: null, failed: null }
      : null;
    setProgressError(false);
  }, [docId, isGuest, token]);

  const drainProgress = useCallback(async (writer: ProgressWriter) => {
    if (writer.inFlight) return;
    writer.inFlight = true;
    try {
      while (writer.queued) {
        const chapterKey = writer.queued;
        writer.queued = null;
        try {
          await putReadingProgress(writer.token, writer.docId, chapterKey);
        } catch {
          // If the user moved again while this save was in flight, discard the
          // older failed location and try the already-coalesced latest one.
          if (writer.queued) continue;
          writer.failed = chapterKey;
          if (progressWriterRef.current === writer) setProgressError(true);
          break;
        }
      }
    } finally {
      writer.inFlight = false;
      if (writer.queued && !writer.failed) void drainProgress(writer);
    }
  }, []);

  useEffect(() => {
    if (!initialResolved || resolvedDocId !== docId || !currentKey) return;
    const writer = progressWriterRef.current;
    if (!writer || writer.docId !== docId || writer.token !== token) return;
    writer.queued = currentKey;
    writer.failed = null;
    setProgressError(false);
    void drainProgress(writer);
  }, [currentKey, docId, drainProgress, initialResolved, resolvedDocId, token]);

  const retryProgress = useCallback(() => {
    const writer = progressWriterRef.current;
    if (!writer?.failed) return;
    writer.queued = writer.failed;
    writer.failed = null;
    setProgressError(false);
    void drainProgress(writer);
  }, [drainProgress]);

  useEffect(() => {
    if (highlight && chapters.length === 1) {
      document.getElementById(`anchor-${highlight}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [chapters, highlight]);

  const loadChapter = useCallback(async (key: string, mode: "append" | "replace") => {
    if (!token && !guestToken) return;
    if (mode === "append" && replacePendingRef.current) return;
    if (mode === "append" && (requestedRef.current.has(key) || pendingAppendsRef.current.has(key))) return;
    const requestId = ++chapterRequestRef.current;
    if (mode === "replace") replacePendingRef.current = true;
    else pendingAppendsRef.current.set(key, requestId);
    setChapterLoading(key);
    setChapterError(null);
    try {
      const chapter = await getReaderChapter(token ?? "", docId, { chapter: key, guestToken: guestToken || undefined });
      if (requestId !== chapterRequestRef.current) return;
      setChapters((previous) => {
        if (mode === "replace") return [chapter];
        if (previous.some((item) => item.chapter_key === key)) return previous;
        return [...previous, chapter];
      });
      if (mode === "append") requestedRef.current.add(chapter.chapter_key);
      if (mode === "replace") {
        requestedRef.current = new Set([chapter.chapter_key]);
        setCurrentKey(chapter.chapter_key);
        setHighlight(null);
        scrollRef.current?.scrollTo({ top: 0 });
      }
    } catch {
      if (requestId !== chapterRequestRef.current) return;
      setChapterError({ key, mode });
    } finally {
      if (mode === "append" && pendingAppendsRef.current.get(key) === requestId) {
        pendingAppendsRef.current.delete(key);
      }
      if (requestId === chapterRequestRef.current) {
        replacePendingRef.current = false;
        setChapterLoading(null);
      }
    }
  }, [docId, guestToken, token]);

  const jump = useCallback((key: string) => {
    void loadChapter(key, "replace");
  }, [loadChapter]);

  function onScroll(event: React.UIEvent<HTMLDivElement>) {
    const element = event.currentTarget;
    if (!replacePendingRef.current && element.scrollHeight - element.scrollTop - element.clientHeight < 600) {
      const last = chapters[chapters.length - 1];
      if (last?.next_chapter_key && !chapters.some((chapter) => chapter.chapter_key === last.next_chapter_key)) {
        void loadChapter(last.next_chapter_key, "append");
      }
    }
    const containerTop = element.getBoundingClientRect().top;
    let visibleKey = currentKey;
    element.querySelectorAll("section[data-chapter-key]").forEach((section) => {
      if (section.getBoundingClientRect().top - containerTop <= 80) visibleKey = section.getAttribute("data-chapter-key");
    });
    if (visibleKey && visibleKey !== currentKey) setCurrentKey(visibleKey);
  }

  function goBack() {
    setShowBackGuide(false);
    if (isGuest) {
      consumeReaderReturnKey(returnKey, origin);
      router.push(params.get("preview") === "1" ? "/search/guest?preview=1" : "/search/guest");
      return;
    }
    const fallback = origin === "saved" ? "/bookmarks" : origin === "history" ? "/history" : origin === "search" ? "/search" : "/sources";
    if (consumeReaderReturnKey(returnKey, origin)) router.back();
    else router.push(fallback);
  }

  function browseSections() {
    const next = new URLSearchParams({ from: origin });
    if (isReaderReturnKey(returnKey)) next.set("returnKey", returnKey);
    if (isGuest && params.get("preview") === "1") next.set("preview", "1");
    if (isGuest && params.get("guideBack") === "1") next.set("guideBack", "1");
    router.replace(`${isGuest ? "/reader/guest" : "/reader"}/${docId}?${next.toString()}`);
  }

  function reportContent() {
    if (isGuest) {
      guestGate?.requestSignup("feature");
      return;
    }
    saveFeedbackContext({ category: "content", origin: "reader", route: "/reader", document_id: docId });
    router.push("/feedback");
  }

  if (error) {
    return (
      <div className="flex h-full flex-col bg-brand-bg">
        <ReaderMobileStatusHeader />
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <p className="text-sm text-brand-muted">This document couldn&apos;t be loaded.</p>
          <div className="flex items-center gap-4">
            <button onClick={() => setInitialRetryKey((value) => value + 1)} className="text-sm font-medium text-brand-accent hover:underline">Try again</button>
            <button onClick={goBack} className="text-sm text-brand-muted hover:text-brand-accent">← Back</button>
          </div>
        </div>
      </div>
    );
  }
  if (loading && !doc) {
    return <ReaderPageSkeleton />;
  }
  if (!doc) return <ReaderMobileStatusHeader />;

  const fontPixels = fontSize === "small" ? "14px" : fontSize === "large" ? "18px" : "16px";
  const lineHeight = spacing === "compact" ? "1.55" : spacing === "relaxed" ? "2.1" : "1.8";

  return (
    <div className="flex h-full flex-col bg-brand-bg">
      <ReaderChrome
        document={doc}
        toc={toc}
        currentChapterKey={currentKey}
        backLabel={backLabel}
        onBack={goBack}
        onBrowseSections={browseSections}
        onJump={jump}
        fontSize={fontSize}
        spacing={spacing}
        onFontSizeChange={changeFontSize}
        onSpacingChange={changeSpacing}
        onReportContent={reportContent}
        showBackGuide={showBackGuide}
        onDismissBackGuide={() => setShowBackGuide(false)}
      />
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="reader-content flex-1 overflow-y-auto"
        style={{ "--reader-font-size": fontPixels, "--reader-line-height": lineHeight } as React.CSSProperties}
      >
        {chapters.map((chapter) => <ChapterSection key={chapter.chapter_key} chapter={chapter} highlightAnchor={highlight} />)}
        {chapterLoading && (
          <div className="animate-pulse space-y-3 px-6 py-8" aria-label="Loading chapter">
            <div className="h-4 w-2/3 rounded bg-brand-surface" />
            <div className="h-4 w-full rounded bg-brand-surface" />
            <div className="h-4 w-5/6 rounded bg-brand-surface" />
          </div>
        )}
        {chapterError && (
          <div className="px-6 py-6 text-center">
            <p className="mb-2 text-sm text-brand-muted">Chapter couldn&apos;t be loaded.</p>
            <button className="text-sm text-brand-accent hover:underline" onClick={() => void loadChapter(chapterError.key, chapterError.mode)}>Retry</button>
          </div>
        )}
        {progressError && (
          <div role="status" className="sticky bottom-3 mx-auto mb-3 flex w-fit items-center gap-3 rounded-md border border-brand-muted/30 bg-brand-surface px-3 py-2 text-xs text-brand-muted shadow-lg">
            <span>Your reading place has not synced yet.</span>
            <button type="button" onClick={retryProgress} className="font-medium text-brand-accent hover:underline">Retry</button>
          </div>
        )}
      </div>
    </div>
  );
}

export function DocumentReader({ docId, isGuest = false, initialMode = "overview" }: { docId: string; isGuest?: boolean; initialMode?: "overview" | "chapter" }) {
  const fallback = initialMode === "chapter" ? <ReaderChapterSkeleton /> : <ReaderOverviewSkeleton />;
  return <Suspense fallback={fallback}><ReaderEntry docId={docId} isGuest={isGuest} /></Suspense>;
}

function ReaderEntry({ docId, isGuest }: { docId: string; isGuest: boolean }) {
  const params = useSearchParams();
  if (!params.get("anchor") && !params.get("chapter")) {
    return <DocumentOverview docId={docId} mobileHeader={<ReaderMobileStatusHeader />} isGuest={isGuest} />;
  }
  return <Inner docId={docId} isGuest={isGuest} />;
}
