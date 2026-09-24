"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import {
  putReadingProgress,
  type DocumentInfo,
  type ReaderChapter,
  type TocEntry,
} from "@/lib/api";
import {
  invalidateReaderDocument,
  isChapterCached,
  isNotFoundError,
  loadChapter as loadCachedChapter,
  loadEntryChapter,
  loadToc,
  prefetchChapter,
  type ReaderAccess,
} from "@/lib/reader-cache";
import { ChapterSection } from "./ChapterSection";
import { ReaderChrome, type ReaderFontSize, type ReaderSpacing } from "./ReaderChrome";
import { saveFeedbackContext } from "@/lib/feedbackContext";
import { ReaderChapterSkeleton, ReaderOverviewSkeleton, ReaderPageSkeleton } from "@/components/common/PageSkeletons";
import { DocumentOverview } from "./DocumentOverview";
import { consumeReaderReturnKey, isReaderReturnKey, type ReaderOrigin } from "@/lib/readerNavigation";
import { getGuestSessionToken } from "@/lib/trial";
import { ReaderMobileStatusHeader } from "./ReaderMobileStatusHeader";

const ORIGINS = new Set(["search", "saved", "library", "history"]);

function whenIdle(callback: () => void): () => void {
  if (typeof window.requestIdleCallback === "function") {
    const handle = window.requestIdleCallback(callback, { timeout: 2000 });
    return () => window.cancelIdleCallback(handle);
  }
  const handle = window.setTimeout(callback, 200);
  return () => window.clearTimeout(handle);
}

function saveDataRequested(): boolean {
  return (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true;
}

interface ProgressWriter {
  token: string;
  docId: string;
  inFlight: boolean;
  queued: string | null;
  failed: string | null;
}

function Inner({ docId, isGuest = false }: { docId: string; isGuest?: boolean }) {
  const { token } = useAppContext();
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
  const [toc, setToc] = useState<TocEntry[] | null>(null);
  const [tocDocument, setTocDocument] = useState<DocumentInfo | null>(null);
  const [tocFailed, setTocFailed] = useState(false);
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
  const tocControllerRef = useRef<AbortController | null>(null);
  const tocRevalidatedRef = useRef(false);
  const tocShownRef = useRef(false);
  // Requests read the token through a ref so a routine token refresh does not
  // re-run the load effect, which would drop appended chapters and return the
  // reader to the chapter it was opened at.
  const tokenRef = useRef(token);
  const canRead = Boolean(token) || Boolean(guestToken);

  useEffect(() => { tokenRef.current = token; }, [token]);
  useEffect(() => { if (isGuest) queueMicrotask(() => setGuestToken(getGuestSessionToken())); }, [isGuest]);

  const readerAccess = useCallback((): ReaderAccess => ({
    token: tokenRef.current,
    guestToken: guestToken || undefined,
  }), [guestToken]);

  // The table of contents only feeds the chrome (position, Previous/Next), so it
  // loads beside the chapter and never holds it back. A background refresh keeps
  // whatever contents are already showing if it fails; with none showing yet, a
  // failure must still surface so the chrome can offer a retry.
  const requestToc = useCallback((refresh = false) => {
    const background = refresh && tocShownRef.current;
    tocControllerRef.current?.abort();
    const controller = new AbortController();
    tocControllerRef.current = controller;
    if (!background) setTocFailed(false);
    loadToc(readerAccess(), docId, controller.signal).then((response) => {
      if (tocControllerRef.current !== controller) return;
      tocShownRef.current = true;
      setTocDocument(response.document);
      setToc(response.chapters);
      setTocFailed(false);
    }, () => {
      if (tocControllerRef.current !== controller || background) return;
      setTocFailed(true);
    });
  }, [docId, readerAccess]);

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
    if (!canRead) return;
    const controller = new AbortController();
    let alive = true;
    const access = readerAccess();
    chapterRequestRef.current += 1;
    replacePendingRef.current = false;
    tocRevalidatedRef.current = false;
    tocShownRef.current = false;
    setInitialResolved(false);
    setResolvedDocId(null);
    setError(null);
    setLoading(true);
    setDoc(null);
    setToc(null);
    setTocDocument(null);
    setChapters([]);
    setCurrentKey(null);
    pendingAppendsRef.current.clear();
    setHighlight(initialAnchor);
    requestToc();
    (async () => {
      try {
        // ReaderEntry shows the overview unless the URL names an anchor or a
        // chapter, so one of the two is always present here. Resuming at saved
        // progress is the overview's "Continue at" action, not this path's.
        let chapter: ReaderChapter;
        try {
          chapter = initialAnchor
            ? await loadEntryChapter(access, docId, { anchor: initialAnchor, signal: controller.signal })
            : await loadCachedChapter(access, docId, initialChapter!, controller.signal);
        } catch (caught) {
          if (isNotFoundError(caught)) invalidateReaderDocument(access, docId);
          throw caught;
        }
        if (!alive) return;
        setDoc(chapter.document);
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
      tocControllerRef.current?.abort();
      tocControllerRef.current = null;
      chapterRequestRef.current += 1;
      replacePendingRef.current = false;
    };
  }, [canRead, docId, initialAnchor, initialChapter, initialRetryKey, isGuest, readerAccess, requestToc]);

  // Both responses carry the document's passage count. If they disagree, the
  // corpus was republished while one of them sat in the cache. Either could be
  // the stale one, so drop all of the document's cached data and fetch the
  // contents again, once per open; a stale chapter already on screen stays until
  // the reader moves, and that load then comes from the server.
  useEffect(() => {
    // In the commit that switches documents, chapters still belong to the old one.
    if (!tocDocument || tocRevalidatedRef.current || resolvedDocId !== docId) return;
    if (chapters.every((item) => item.document.chunk_count === tocDocument.chunk_count)) return;
    tocRevalidatedRef.current = true;
    invalidateReaderDocument(readerAccess(), docId);
    requestToc(true);
  }, [chapters, docId, readerAccess, requestToc, resolvedDocId, tocDocument]);

  // Warm the chapter after the last one shown, so Next and scrolling on are
  // served from memory. Moving elsewhere cancels a prefetch still in flight,
  // without affecting a load that has already joined it.
  useEffect(() => {
    // In the commit that switches documents, chapters still belong to the old one.
    const nextKey = resolvedDocId === docId ? chapters[chapters.length - 1]?.next_chapter_key : null;
    if (!nextKey || chapters.some((item) => item.chapter_key === nextKey)) return;
    const access = readerAccess();
    if (!access.token && !access.guestToken) return;
    if (isChapterCached(access, docId, nextKey) || saveDataRequested()) return;
    const controller = new AbortController();
    const cancel = whenIdle(() => prefetchChapter(access, docId, nextKey, controller.signal));
    return () => {
      cancel();
      controller.abort();
    };
  }, [chapters, docId, readerAccess, resolvedDocId]);

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
    const access = readerAccess();
    if (!access.token && !access.guestToken) return;
    if (mode === "append" && replacePendingRef.current) return;
    if (mode === "append" && (requestedRef.current.has(key) || pendingAppendsRef.current.has(key))) return;
    const requestId = ++chapterRequestRef.current;
    if (mode === "replace") replacePendingRef.current = true;
    else pendingAppendsRef.current.set(key, requestId);
    // A chapter already in memory swaps in without flashing the loading skeleton.
    setChapterLoading(isChapterCached(access, docId, key) ? null : key);
    setChapterError(null);
    try {
      const chapter = await loadCachedChapter(access, docId, key);
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
    } catch (caught) {
      // A missing chapter usually means the contents in memory predate a
      // republish; refresh them so the reader can navigate by current keys.
      if (isNotFoundError(caught)) invalidateReaderDocument(access, docId);
      if (requestId !== chapterRequestRef.current) return;
      if (isNotFoundError(caught)) requestToc(true);
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
  }, [docId, readerAccess, requestToc]);

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
      saveFeedbackContext({ category: "content", origin: "reader", route: "/reader", document_id: docId });
      router.push("/guest/feedback");
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

  const currentChapter = chapters.find((item) => item.chapter_key === currentKey) ?? null;
  const fontPixels = fontSize === "small" ? "14px" : fontSize === "large" ? "18px" : "16px";
  const lineHeight = spacing === "compact" ? "1.55" : spacing === "relaxed" ? "2.1" : "1.8";

  return (
    <div className="flex h-full flex-col bg-brand-bg">
      <ReaderChrome
        document={doc}
        toc={toc ?? []}
        tocStatus={toc ? "ready" : tocFailed ? "error" : "loading"}
        onRetryToc={() => requestToc()}
        currentChapter={currentChapter}
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
            <span>We couldn&apos;t save your reading place yet.</span>
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
