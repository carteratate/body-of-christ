"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { BookOpen, ChevronLeft, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { getReadingProgress, ReaderMovedError, ReaderRemovedError, ReaderRestrictedError, type ContentsNode, type DocumentInfo, type ReadingProgress, type TocEntry } from "@/lib/api";
import { loadToc } from "@/lib/reader-cache";
import { ReaderRestrictedNotice } from "./ReaderRestrictedNotice";
import { ReaderRemovedNotice } from "./ReaderRemovedNotice";
import { certaintyTag, formatAttribution, formatDate, formatKind, formatTranslation, factNotes, type WorkInfo } from "@/lib/attribution";
import type { Tombstone } from "@/lib/corpus-lifecycle";
import { SourceCredit } from "@/components/common/SourceLink";
import { getCollectionMeta } from "@/lib/collections";
import { LIFT } from "@/lib/lift";
import { hasReaderReturnMarker, isReaderReturnKey, movedReaderHref, type ReaderOrigin } from "@/lib/readerNavigation";
import { NavPendingBar } from "@/components/common/NavPending";
import { useReaderBack } from "./useReaderBack";
import { getGuestSessionToken } from "@/lib/trial";
import { countByKind, normalizeForSearch } from "@/lib/contents-tree";
import { ContentsTree } from "./ContentsTree";

const ORIGINS = new Set(["search", "saved", "library", "history"]);
const SECTION_BATCH_SIZE = 30;

const KIND_PLURALS: Record<string, string> = {
  part: "parts", treatise: "treatises", section: "sections", chapter: "chapters",
  question: "questions", article: "articles",
};

/** "6 parts · 612 questions · 3,120 articles", in the order the kinds first appear. */
function treeSummary(nodes: ContentsNode[]): string {
  return [...countByKind(nodes)]
    .filter(([kind]) => kind in KIND_PLURALS)
    .map(([kind, count]) => `${count.toLocaleString()} ${count === 1 ? kind : KIND_PLURALS[kind]}`)
    .join(" · ");
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
  const term = normalizeForSearch(rawQuery.trim());
  if (!term) return true;
  if (collection === "catechism" && /^\d+$/.test(term)) {
    const paragraph = Number(term);
    const bounds = entry.chapter_label.match(/(\d[\d,]*)\s*[–—-]\s*(\d[\d,]*)/);
    if (!bounds) return false;
    const start = Number(bounds[1].replaceAll(",", ""));
    const end = Number(bounds[2].replaceAll(",", ""));
    return Number.isFinite(start) && Number.isFinite(end) && paragraph >= start && paragraph <= end;
  }
  return normalizeForSearch(entry.chapter_label).includes(term);
}

interface Props {
  docId: string;
  mobileHeader: ReactNode;
  isGuest?: boolean;
}

export function DocumentOverview({ docId, mobileHeader, isGuest = false }: Props) {
  const { token } = useAppContext();
  const params = useSearchParams();
  // Read through a ref: the load effect must not re-run when the router object does.
  const router = useRouter();
  const routerRef = useRef(router);
  const guideBack = params.get("guideBack") === "1";
  const preview = params.get("preview") === "1";
  const originParam = params.get("from");
  const origin = (originParam && ORIGINS.has(originParam) ? originParam : "library") as ReaderOrigin;
  const returnKey = params.get("returnKey");
  const [documentInfo, setDocumentInfo] = useState<DocumentInfo | null>(null);
  const [chapters, setChapters] = useState<TocEntry[]>([]);
  const [contents, setContents] = useState<ContentsNode[] | null>(null);
  const [progress, setProgress] = useState<ReadingProgress | null>(null);
  const [query, setQuery] = useState("");
  const [visibleLimit, setVisibleLimit] = useState(SECTION_BATCH_SIZE);
  const [resolvedRequest, setResolvedRequest] = useState<string | null>(null);
  const [failedRequest, setFailedRequest] = useState<string | null>(null);
  // The request the API refused because the document is excerpt-only (issue #265).
  const [restricted, setRestricted] = useState<{ request: string; sourceUrl: string | null } | null>(null);
  // The request the API answered 410: the document was removed (2.4a).
  const [removed, setRemoved] = useState<{ request: string; tombstone: Tombstone } | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [guestToken, setGuestToken] = useState("");
  const requestRef = useRef(0);
  // Keyed by who is reading, not by the access token itself: the hourly token
  // refresh must not reload the overview, which clears the section search and
  // collapses "Show more". Requests read the current token through a ref.
  const tokenRef = useRef(token);
  const signedIn = Boolean(token);
  const requestKey = `${signedIn ? "signed-in" : guestToken || "signed-out"}:${docId}:${retryKey}`;

  useEffect(() => { tokenRef.current = token; }, [token]);
  useEffect(() => { routerRef.current = router; }, [router]);
  useEffect(() => { if (isGuest) queueMicrotask(() => setGuestToken(getGuestSessionToken())); }, [isGuest]);

  useEffect(() => {
    const requestToken = tokenRef.current;
    if (!signedIn && !guestToken) return;
    const requestId = ++requestRef.current;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);
    // Shared with DocumentReader, so opening a section after this overview (or
    // returning to it) reuses the contents instead of downloading them again.
    const tocRequest = loadToc({ token: requestToken, guestToken: guestToken || undefined }, docId, controller.signal);
    const progressRequest = isGuest ? Promise.resolve(null) : getReadingProgress(requestToken!, docId, controller.signal);

    void tocRequest.then((toc) => {
      if (requestId !== requestRef.current) return;
      setDocumentInfo(toc.document);
      setChapters(toc.chapters);
      setContents(toc.contents?.length ? toc.contents : null);
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
    }).catch((caught) => {
      if (requestId !== requestRef.current) return;
      if (caught instanceof ReaderMovedError) {
        // The document moved: open where it went, keeping how the reader was entered.
        routerRef.current.replace(movedReaderHref(caught.redirect, { origin, returnKey, isGuest, guideBack, preview }));
        return;
      }
      if (caught instanceof ReaderRestrictedError) setRestricted({ request: requestKey, sourceUrl: caught.sourceUrl });
      if (caught instanceof ReaderRemovedError) setRemoved({ request: requestKey, tombstone: caught.tombstone });
      setFailedRequest(requestKey);
    });

    void Promise.allSettled([tocRequest, progressRequest]).then(() => clearTimeout(timeout));

    return () => {
      clearTimeout(timeout);
      controller.abort();
      requestRef.current += 1;
    };
  }, [docId, guestToken, guideBack, isGuest, origin, preview, requestKey, retryKey, returnKey, signedIn]);

  const loading = resolvedRequest !== requestKey && failedRequest !== requestKey;
  const error = failedRequest === requestKey;

  const matchingChapters = useMemo(() => {
    if (contents) return [];   // the tree does its own filtering
    return chapters
      .map((entry, index) => ({ entry, ordinal: index + 1 }))
      .filter(({ entry }) => matchesSection(entry, query, documentInfo?.collection ?? ""));
  }, [chapters, contents, documentInfo?.collection, query]);
  const visibleChapters = matchingChapters.slice(0, visibleLimit);

  function openChapter(chapterKey: string, anchor?: string | null) {
    const next = new URLSearchParams({ from: origin, chapter: chapterKey });
    if (anchor) next.set("anchor", anchor);
    if (isReaderReturnKey(returnKey)) next.set("returnKey", returnKey);
    if (isGuest && params.get("preview") === "1") next.set("preview", "1");
    if (isGuest && params.get("guideBack") === "1") next.set("guideBack", "1");
    const destination = `${isGuest ? "/reader/guest" : "/reader"}/${encodeURIComponent(docId)}?${next.toString()}`;
    // Same route, different search params: the History API skips the server
    // round trip that router.push/replace would make (see DocumentReader).
    // Replace only when this tab entered through an in-app link (a live marker),
    // so Back returns to that page. A key without a marker (a cmd-click tab, a
    // pasted URL) pushes, so browser Back returns to this overview.
    if (hasReaderReturnMarker(returnKey, origin)) window.history.replaceState(null, "", destination);
    else window.history.pushState(null, "", destination);
  }

  const { goBack, pending: backPending } = useReaderBack({ isGuest, origin, returnKey, preview: params.get("preview") === "1" });

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

  if (error && removed?.request === requestKey) {
    return (
      <ReaderRemovedNotice
        tombstone={removed.tombstone}
        header={mobileHeader}
        onBack={goBack}
        backPending={backPending}
        isGuest={isGuest}
      />
    );
  }

  if (error && restricted?.request === requestKey) {
    return (
      <ReaderRestrictedNotice
        sourceUrl={restricted.sourceUrl}
        header={mobileHeader}
        onBack={goBack}
        backPending={backPending}
      />
    );
  }

  if (error || !documentInfo || chapters.length === 0) {
    return (
      <div className="flex h-full flex-col bg-brand-bg">
        {mobileHeader}
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
          <p className="text-sm text-brand-muted">This document overview couldn&apos;t be loaded.</p>
          <div className="flex gap-4">
            <button type="button" onClick={goBack} aria-busy={backPending || undefined} className="relative text-sm text-brand-muted hover:text-brand-primary">← Back<NavPendingBar pending={backPending} /></button>
            <button type="button" onClick={() => setRetryKey((value) => value + 1)} className="text-sm font-medium text-brand-accent hover:underline">Retry</button>
          </div>
        </div>
      </div>
    );
  }

  const collectionMeta = getCollectionMeta(documentInfo.collection);
  const language = sectionLanguage(documentInfo.collection);
  const facts = documentInfo.facts ?? null;
  const attribution = [
    formatAttribution(documentInfo.author, facts),
    formatDate(facts, documentInfo.year),
    // Without facts the line is today's, code and all.
    facts ? formatTranslation(facts.translation ?? documentInfo.translation) : documentInfo.translation,
  ].filter(Boolean).join(" · ");
  const certainty = certaintyTag(facts?.certainty);
  const kind = formatKind(facts);
  const notes = factNotes(facts);
  const superseded = facts?.superseded_note?.trim() || null;
  const works = documentInfo.works ?? [];
  const credit = facts?.source_credit?.trim() || null;

  return (
    <div className="flex h-full min-w-0 flex-col bg-brand-bg">
      {mobileHeader}
      <div className="flex-1 overflow-y-auto">
        <main className="mx-auto w-full min-w-0 max-w-3xl px-4 py-5 sm:px-6 sm:py-7">
          {/* Styled as the reader's own Back and Browse buttons (ReaderChrome). */}
          <button type="button" onClick={goBack} aria-busy={backPending || undefined} className="relative mb-5 flex min-h-9 w-fit items-center gap-1 rounded-md border border-brand-accent px-3 text-xs font-semibold text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
            <ChevronLeft size={16} aria-hidden="true" /> Back to {backLabel}
            <NavPendingBar pending={backPending} />
          </button>

          <section className="rounded-lg border border-brand-muted/20 bg-brand-surface p-5 sm:p-7">
            <span className="inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold" style={{ color: collectionMeta?.color, borderColor: collectionMeta?.color }}>
              {collectionMeta?.label ?? documentInfo.collection}
            </span>
            <h1 className="mt-3 font-brand text-2xl font-semibold text-brand-accent sm:text-3xl">{documentInfo.title}</h1>
            {attribution && (
              <p className="mt-1 text-sm text-brand-muted">
                {attribution}
                {certainty && <span className="ml-2 rounded border border-brand-muted/40 px-1 text-[11px]">{certainty}</span>}
              </p>
            )}
            {kind && <p className="mt-1 text-sm text-brand-muted" data-testid="document-kind">{kind}</p>}
            {(notes.length > 0 || superseded) && (
              <div className="mt-3 space-y-1 text-sm leading-snug text-brand-muted">
                {notes.map((note) => <p key={note}>{note}</p>)}
                {superseded && (
                  <p>
                    {superseded}
                    {facts?.superseded_by && !isGuest && (
                      <> <a href={movedReaderHref({ document_id: facts.superseded_by }, { origin, returnKey: null, isGuest, guideBack: false, preview: false })} className="text-brand-accent hover:underline">Read the current text</a></>
                    )}
                  </p>
                )}
              </div>
            )}
            {works.length > 0 && <WorksList works={works} />}
            <p className="mt-3 text-sm text-brand-muted">
              {documentInfo.chunk_count.toLocaleString()} passages · {contents
                ? treeSummary(contents)
                : `${chapters.length.toLocaleString()} ${chapters.length === 1 ? language.singular : language.plural}`}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {progress && (
                <button type="button" onClick={() => openChapter(progress.chapter_key)} className="inline-flex min-h-11 items-center gap-2 rounded-md bg-brand-accent px-4 py-2 text-sm font-semibold text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary">
                  <BookOpen size={17} aria-hidden="true" /> Continue at {progress.chapter_label}
                </button>
              )}
              {/* With saved progress, "Continue at" is the only action: the contents below
                  already lead back to the beginning. */}
              {!progress && (
                <button type="button" onClick={() => openChapter(chapters[0].chapter_key)} className="min-h-11 rounded-md bg-brand-accent px-4 py-2 text-sm font-medium text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
                  Start reading
                </button>
              )}
            </div>
            {credit && <SourceCredit text={credit} />}
          </section>

          {contents ? (
          <section className="mt-7 rounded-lg border border-brand-muted/20 bg-brand-surface p-4 sm:p-6" aria-labelledby="overview-contents-heading">
            <div className="mb-3">
              <h2 id="overview-contents-heading" className="text-lg font-semibold text-brand-primary">Contents</h2>
              <p className="mt-1 text-xs text-brand-muted">Expand a part to find a place, or search the headings.</p>
            </div>
            <label className="mb-3 flex min-w-0 items-center gap-2 rounded-md border border-brand-muted/30 bg-brand-surface px-3 focus-within:border-brand-accent">
              <Search size={17} className="shrink-0 text-brand-muted" aria-hidden="true" />
              <span className="sr-only">Search contents</span>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search contents"
                className="min-w-0 flex-1 bg-transparent py-3 text-brand-primary outline-none placeholder:text-brand-muted"
              />
            </label>
            {/* Every branch starts closed, so a reader picks a Part first; "Continue at"
                resumes saved progress. */}
            <ContentsTree
              key={documentInfo.id}
              nodes={contents}
              filter={query}
              onOpen={(node) => openChapter(node.chapter_key, node.anchor)}
            />
          </section>
          ) : (
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
                      <button key={entry.chapter_key} type="button" onClick={() => openChapter(entry.chapter_key)} aria-label={`${documentInfo.title} chapter ${bibleChapterLabel(entry)}`} className={`flex aspect-square w-full items-center justify-center rounded-md border border-brand-muted/25 bg-brand-bg text-sm font-medium text-brand-primary ${LIFT}`}>
                        {bibleChapterLabel(entry)}
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="grid min-w-0 gap-2 sm:grid-cols-2">
                    {visibleChapters.map(({ entry, ordinal }) => (
                      <button key={entry.chapter_key} type="button" onClick={() => openChapter(entry.chapter_key)} className={`flex min-h-12 min-w-0 items-start gap-3 rounded-md border border-brand-muted/20 bg-brand-surface px-3 py-3 text-left ${LIFT}`}>
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
          )}
        </main>
      </div>
    </div>
  );
}

/** The works inside a document (D6), each with its own attribution. */
function WorksList({ works }: { works: WorkInfo[] }) {
  return (
    <div className="mt-4">
      <h2 className="text-xs font-semibold uppercase tracking-[0.08em] text-brand-muted">Works in this volume</h2>
      <ul className="mt-2 space-y-1.5 text-sm">
        {works.map((work) => {
          const label = [
            formatAttribution(work.author, { certainty: work.certainty }, null, { certainty: false }),
            formatDate({ date_display: work.date_display, year: work.year }),
          ].filter(Boolean).join(" · ");
          const tag = certaintyTag(work.certainty);
          const notes = factNotes({ attribution_note: work.attribution_note, notes: work.notes });
          return (
            <li key={work.work_key}>
              <span className="text-brand-primary">{work.title}</span>
              {label && <span className="ml-2 text-xs text-brand-muted">{label}</span>}
              {tag && <span className="ml-1.5 rounded border border-brand-muted/40 px-1 text-[10px] text-brand-muted">{tag}</span>}
              {notes.map((note) => <p key={note} className="text-xs leading-snug text-brand-muted">{note}</p>)}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
