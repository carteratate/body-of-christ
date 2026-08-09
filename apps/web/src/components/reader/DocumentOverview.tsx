"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, BookOpen, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { getReadingProgress, getToc, type DocumentInfo, type ReadingProgress, type TocEntry } from "@/lib/api";
import { getCollectionMeta } from "@/lib/collections";
import { consumeReaderReturnKey, isReaderReturnKey, type ReaderOrigin } from "@/lib/readerNavigation";

const ORIGINS = new Set(["search", "saved", "library", "history"]);
const SECTION_BATCH_SIZE = 30;

function normalize(value: string): string {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

function sectionLanguage(collection: string): { singular: string; plural: string; prompt: string } {
  if (collection === "bible") return { singular: "chapter", plural: "chapters", prompt: "Choose a chapter" };
  if (collection === "catechism") return { singular: "paragraph range", plural: "paragraph ranges", prompt: "Choose a paragraph range" };
  if (collection === "summa") return { singular: "article", plural: "articles", prompt: "Choose an article" };
  if (collection === "canon-law") return { singular: "section", plural: "sections", prompt: "Choose a book or section" };
  return { singular: "section", plural: "sections", prompt: "Choose a section" };
}

function bibleChapterLabel(entry: TocEntry): string {
  return entry.chapter_label.match(/(\d+)\s*$/)?.[1] ?? entry.chapter_label;
}

function matchesSection(entry: TocEntry, rawQuery: string, collection: string): boolean {
  const term = normalize(rawQuery.trim());
  if (!term) return true;
  if (collection === "catechism" && /^\d+$/.test(term)) {
    const paragraph = Number(term);
    const bounds = entry.chapter_label.match(/(\d[\d,]*)\s*[–—-]\s*(\d[\d,]*)/);
    if (!bounds) return false;
    const start = Number(bounds[1].replaceAll(",", ""));
    const end = Number(bounds[2].replaceAll(",", ""));
    return Number.isFinite(start) && Number.isFinite(end) && paragraph >= start && paragraph <= end;
  }
  return normalize(entry.chapter_label).includes(term);
}

interface Props {
  docId: string;
  mobileHeader: ReactNode;
}

export function DocumentOverview({ docId, mobileHeader }: Props) {
  const { token } = useAppContext();
  const router = useRouter();
  const params = useSearchParams();
  const originParam = params.get("from");
  const origin = (originParam && ORIGINS.has(originParam) ? originParam : "library") as ReaderOrigin;
  const returnKey = params.get("returnKey");
  const [documentInfo, setDocumentInfo] = useState<DocumentInfo | null>(null);
  const [chapters, setChapters] = useState<TocEntry[]>([]);
  const [progress, setProgress] = useState<ReadingProgress | null>(null);
  const [query, setQuery] = useState("");
  const [visibleLimit, setVisibleLimit] = useState(SECTION_BATCH_SIZE);
  const [resolvedRequest, setResolvedRequest] = useState<string | null>(null);
  const [failedRequest, setFailedRequest] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const requestRef = useRef(0);
  const requestKey = `${token ?? "signed-out"}:${docId}:${retryKey}`;

  useEffect(() => {
    if (!token) return;
    const requestId = ++requestRef.current;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);
    const tocRequest = getToc(token, docId, controller.signal);
    const progressRequest = getReadingProgress(token, docId, controller.signal);

    void tocRequest.then((toc) => {
      if (requestId !== requestRef.current) return;
      setDocumentInfo(toc.document);
      setChapters(toc.chapters);
      setProgress(null);
      setQuery("");
      setVisibleLimit(SECTION_BATCH_SIZE);
      setFailedRequest(null);
      setResolvedRequest(requestKey);

      void progressRequest.then((nextProgress) => {
        if (
          requestId === requestRef.current
          && nextProgress
          && toc.chapters.some((entry) => entry.chapter_key === nextProgress.chapter_key)
        ) setProgress(nextProgress);
      }).catch(() => undefined);
    }).catch(() => {
      if (requestId === requestRef.current) setFailedRequest(requestKey);
    });

    void Promise.allSettled([tocRequest, progressRequest]).then(() => clearTimeout(timeout));

    return () => {
      clearTimeout(timeout);
      controller.abort();
      requestRef.current += 1;
    };
  }, [docId, requestKey, retryKey, token]);

  const loading = resolvedRequest !== requestKey && failedRequest !== requestKey;
  const error = failedRequest === requestKey;

  const matchingChapters = useMemo(() => {
    return chapters
      .map((entry, index) => ({ entry, ordinal: index + 1 }))
      .filter(({ entry }) => matchesSection(entry, query, documentInfo?.collection ?? ""));
  }, [chapters, documentInfo?.collection, query]);
  const visibleChapters = matchingChapters.slice(0, visibleLimit);

  function openChapter(chapterKey: string) {
    const next = new URLSearchParams({ from: origin, chapter: chapterKey });
    if (isReaderReturnKey(returnKey)) next.set("returnKey", returnKey);
    const destination = `/reader/${docId}?${next.toString()}`;
    if (isReaderReturnKey(returnKey)) router.replace(destination);
    else router.push(destination);
  }

  function goBack() {
    const fallback = origin === "saved" ? "/bookmarks" : origin === "history" ? "/history" : origin === "search" ? "/search" : "/sources";
    if (consumeReaderReturnKey(returnKey, origin)) router.back();
    else router.push(fallback);
  }

  const backLabel = origin === "saved" ? "Saved Passages" : origin === "history" ? "Search History" : origin === "search" ? "Search" : "Library";

  if (loading) {
    return (
      <div className="flex h-full flex-col bg-brand-bg">
        {mobileHeader}
        <div className="mx-auto w-full max-w-3xl flex-1 space-y-4 px-4 py-6 sm:px-6">
          <div className="h-5 w-24 animate-pulse rounded bg-brand-surface" />
          <div className="h-10 w-2/3 animate-pulse rounded bg-brand-surface" />
          <div className="h-24 animate-pulse rounded bg-brand-surface" />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => <div key={index} className="h-12 animate-pulse rounded bg-brand-surface" />)}
          </div>
        </div>
      </div>
    );
  }

  if (error || !documentInfo || chapters.length === 0) {
    return (
      <div className="flex h-full flex-col bg-brand-bg">
        {mobileHeader}
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <p className="text-sm text-brand-muted">This document overview couldn&apos;t be loaded.</p>
          <div className="flex gap-4">
            <button type="button" onClick={goBack} className="text-sm text-brand-muted hover:text-brand-primary">← Back</button>
            <button type="button" onClick={() => setRetryKey((value) => value + 1)} className="text-sm font-medium text-brand-accent hover:underline">Retry</button>
          </div>
        </div>
      </div>
    );
  }

  const collectionMeta = getCollectionMeta(documentInfo.collection);
  const language = sectionLanguage(documentInfo.collection);
  const attribution = [documentInfo.author, documentInfo.year, documentInfo.translation].filter(Boolean).join(" · ");

  return (
    <div className="flex h-full min-w-0 flex-col bg-brand-bg">
      {mobileHeader}
      <div className="flex-1 overflow-y-auto">
        <main className="mx-auto w-full min-w-0 max-w-3xl px-4 py-5 sm:px-6 sm:py-7">
          <button type="button" onClick={goBack} className="mb-5 inline-flex items-center gap-1 text-sm text-brand-muted hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
            <ArrowLeft size={16} aria-hidden="true" /> Back to {backLabel}
          </button>

          <section className="rounded-lg border border-brand-muted/20 bg-brand-surface p-5 sm:p-7">
            <span className="inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold" style={{ color: collectionMeta?.color, borderColor: collectionMeta?.color }}>
              {collectionMeta?.label ?? documentInfo.collection}
            </span>
            <h1 className="mt-3 font-brand text-2xl font-semibold text-brand-accent sm:text-3xl">{documentInfo.title}</h1>
            {attribution && <p className="mt-1 text-sm text-brand-muted">{attribution}</p>}
            <p className="mt-3 text-sm text-brand-muted">
              {documentInfo.chunk_count.toLocaleString()} passages · {chapters.length.toLocaleString()} {chapters.length === 1 ? language.singular : language.plural}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {progress && (
                <button type="button" onClick={() => openChapter(progress.chapter_key)} className="inline-flex min-h-11 items-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary">
                  <BookOpen size={17} aria-hidden="true" /> Continue at {progress.chapter_label}
                </button>
              )}
              <button type="button" onClick={() => openChapter(chapters[0].chapter_key)} className={`min-h-11 rounded-md px-4 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${progress ? "border border-brand-accent text-brand-accent hover:bg-brand-accent hover:text-brand-bg" : "bg-brand-accent text-brand-bg"}`}>
                {progress ? "Start from the beginning" : "Start reading"}
              </button>
            </div>
          </section>

          <section className="mt-7 rounded-lg border border-brand-muted/20 bg-brand-surface p-4 sm:p-6" aria-labelledby="overview-contents-heading">
            <div className="mb-3">
              <h2 id="overview-contents-heading" className="text-lg font-semibold text-brand-primary">{language.prompt}</h2>
              <p className="mt-1 text-xs text-brand-muted">Open directly at the place you want to read.</p>
            </div>

            {chapters.length > 12 && (
              <label className="mb-4 flex min-w-0 items-center gap-2 rounded-md border border-brand-muted/30 bg-brand-surface px-3 focus-within:border-brand-accent">
                <Search size={17} className="shrink-0 text-brand-muted" aria-hidden="true" />
                <span className="sr-only">Search {language.plural}</span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setVisibleLimit(SECTION_BATCH_SIZE);
                  }}
                  placeholder={`Search ${language.plural}`}
                  className="min-w-0 flex-1 bg-transparent py-3 text-brand-primary outline-none placeholder:text-brand-muted"
                />
              </label>
            )}

            {matchingChapters.length === 0 ? (
              <div className="rounded-md border border-brand-muted/20 bg-brand-surface px-4 py-8 text-center">
                <p className="text-sm text-brand-muted">No {language.plural} match that search.</p>
                <button type="button" onClick={() => { setQuery(""); setVisibleLimit(SECTION_BATCH_SIZE); }} className="mt-2 text-sm text-brand-accent hover:underline">Clear search</button>
              </div>
            ) : (
              <>
                {documentInfo.collection === "bible" ? (
                  <div className="grid w-full grid-cols-5 gap-2 sm:grid-cols-8 md:grid-cols-10">
                    {visibleChapters.map(({ entry }) => (
                      <button key={entry.chapter_key} type="button" onClick={() => openChapter(entry.chapter_key)} aria-label={`${documentInfo.title} chapter ${bibleChapterLabel(entry)}`} className="flex aspect-square w-full items-center justify-center rounded-md border border-brand-muted/25 bg-brand-bg text-sm font-medium text-brand-primary transition-colors hover:border-brand-accent hover:text-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
                        {bibleChapterLabel(entry)}
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="grid min-w-0 gap-2 sm:grid-cols-2">
                    {visibleChapters.map(({ entry, ordinal }) => (
                      <button key={entry.chapter_key} type="button" onClick={() => openChapter(entry.chapter_key)} className="flex min-h-12 min-w-0 items-start gap-3 rounded-md border border-brand-muted/20 bg-brand-surface px-3 py-3 text-left transition-colors hover:border-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
                        <span className="shrink-0 text-xs font-medium text-brand-accent">{ordinal}</span>
                        <span className="min-w-0 text-sm leading-snug text-brand-primary">{entry.chapter_label}</span>
                      </button>
                    ))}
                  </div>
                )}
                {visibleLimit < matchingChapters.length && (
                  <div className="mt-4 flex flex-col items-center gap-2">
                    <p className="text-xs text-brand-muted">Showing {visibleChapters.length.toLocaleString()} of {matchingChapters.length.toLocaleString()} {language.plural}</p>
                    <button type="button" onClick={() => setVisibleLimit((limit) => limit + SECTION_BATCH_SIZE)} className="min-h-11 rounded-md border border-brand-accent px-4 text-sm font-medium text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
                      Show more {language.plural}
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}
