"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ExternalLink, Search } from "lucide-react";
import { useAppContext } from "@/components/layout/AppShell";
import { LibrarySkeleton } from "@/components/common/PageSkeletons";
import { listReadingProgress, type ReadingProgress, type SourceDocument } from "@/lib/api";
import { COLLECTIONS, getCollectionMeta } from "@/lib/collections";
import { readerHref } from "@/lib/readerNavigation";
import { useReaderReturnKey } from "@/lib/useReaderReturnKey";
import { IntentLink } from "@/components/common";
import { LIFT } from "@/lib/lift";
import { excerptSourceUrl, isExcerptOnly } from "@/lib/reader-access";

/** How the Library's rows link to the reader: one href per document, one same-tab hook. */
interface DocOpener {
  href: (docId: string) => string;
  onNavigate: () => void;
}

// Opens a document: in the reader, or, for an excerpt-only document (issue #265), at
// its official source in a new tab. An excerpt-only document with no known source is
// listed without a link.
function DocLink({ doc, opener, className, children }: {
  doc: SourceDocument;
  opener: DocOpener;
  className: string;
  children: ReactNode;
}) {
  if (isExcerptOnly(doc)) {
    const url = excerptSourceUrl(doc);
    if (!url) return <div className={className}>{children}</div>;
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className={className}
         title="The full text isn't available on TheoCorpus. Read it at the source.">
        {children}
      </a>
    );
  }
  return (
    <IntentLink href={opener.href(doc.id)} onNavigate={opener.onNavigate} className={className}>
      {children}
    </IntentLink>
  );
}

function SourceMark({ doc }: { doc: SourceDocument }) {
  if (!excerptSourceUrl(doc)) return null;
  return (
    <>
      <ExternalLink size={11} aria-hidden="true" className="inline align-baseline ml-1" />
      <span className="sr-only">(opens the source in a new tab)</span>
    </>
  );
}

// Full name for Bible translation codes shown in the sources list.
const TRANSLATION_LABELS: Record<string, string> = {
  "WEB-C": "World English Bible, Catholic Edition",
};

// Canonical Catholic ordering of the 73 books, used to sort the Bible book grid
// (the /v1/sources API returns books alphabetically since they carry no year).
const BOOK_ORDER: string[] = [
  "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
  "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
  "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah", "Tobit", "Judith",
  "Esther", "1 Maccabees", "2 Maccabees",
  "Job", "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon", "Wisdom", "Sirach",
  "Isaiah", "Jeremiah", "Lamentations", "Baruch", "Ezekiel", "Daniel",
  "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
  "Zephaniah", "Haggai", "Zechariah", "Malachi",
  "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
  "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians", "Philippians",
  "Colossians", "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy",
  "Titus", "Philemon", "Hebrews", "James", "1 Peter", "2 Peter",
  "1 John", "2 John", "3 John", "Jude", "Revelation",
];
const BOOK_RANK: Record<string, number> = Object.fromEntries(
  BOOK_ORDER.map((name, i) => [name, i]),
);
function bookRank(title: string): number {
  return BOOK_RANK[title] ?? BOOK_ORDER.length; // unknown titles sort to the end
}

// A collapsible group row: a header you click to expand, revealing a grid of
// clickable child documents. Used for Bible translations → books and for the
// Second Vatican Council → its documents.
function ExpandableGroup({
  open, onToggle, title, subLabel, rightLabel, items, opener,
}: {
  open: boolean;
  onToggle: () => void;
  title: string;
  subLabel: string;
  rightLabel: string;
  items: SourceDocument[];
  opener: DocOpener;
}) {
  return (
    // The toggle raises exactly as the Library's document rows do. The item does not
    // clip its children (that would cut off the toggle's shadow), so the toggle and the
    // open panel round their own corners.
    <li className="rounded bg-brand-surface">
      <button
        onClick={onToggle}
        className={`w-full flex items-start justify-between gap-4 px-3 py-2 rounded text-left bg-brand-surface ${LIFT}`}
      >
        <div className="min-w-0">
          <span className="text-brand-primary text-sm">{title}</span>
          <span className="text-brand-muted text-xs ml-2">{subLabel}</span>
        </div>
        <span className="shrink-0 text-xs text-brand-accent whitespace-nowrap mt-0.5">
          {open ? "▾" : "▸"} {rightLabel}
        </span>
      </button>
      {open && (
        <div className="flex flex-wrap gap-1.5 rounded-b px-3 pb-3 pt-1 border-t border-brand-bg/40">
          {items.map((c) => (
            <DocLink
              key={c.id}
              doc={c}
              opener={opener}
              className="text-xs text-brand-primary bg-brand-bg/60 rounded px-2 py-1 hover:text-brand-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              {c.title}<SourceMark doc={c} />
            </DocLink>
          ))}
        </div>
      )}
    </li>
  );
}

function BibleSection({ docs, opener }: { docs: SourceDocument[]; opener: DocOpener }) {
  const meta = getCollectionMeta("bible");
  const [expanded, setExpanded] = useState<string | null>(null);

  // Group by translation code
  const byTranslation = docs.reduce<Record<string, SourceDocument[]>>((acc, doc) => {
    const key = doc.translation ?? "Unknown";
    if (!acc[key]) acc[key] = [];
    acc[key].push(doc);
    return acc;
  }, {});

  const sectionPassages = docs.reduce((sum, d) => sum + d.chunk_count, 0);

  return (
    <section>
      <div className="flex items-center gap-3 mb-3 pb-2 border-b border-brand-surface">
        <span
          className="text-xs font-semibold px-2.5 py-0.5 rounded-full border"
          style={{ color: meta?.color, borderColor: meta?.color }}
        >
          {meta?.label ?? "bible"}
        </span>
        <span className="text-brand-muted text-xs">
          {Object.keys(byTranslation).length === 1 ? "1 translation" : `${Object.keys(byTranslation).length} translations`}
          {" · "}
          {sectionPassages.toLocaleString()} passages
        </span>
      </div>
      <ul className="space-y-1.5">
        {Object.entries(byTranslation).map(([code, books]) => {
          const totalPassages = books.reduce((sum, b) => sum + b.chunk_count, 0);
          const label = TRANSLATION_LABELS[code] ?? code;
          const orderedBooks = [...books].sort((a, b) => bookRank(a.title) - bookRank(b.title));
          return (
            <ExpandableGroup
              key={code}
              open={expanded === code}
              onToggle={() => setExpanded(expanded === code ? null : code)}
              title={label}
              subLabel={`${books.length} books · ${code}`}
              rightLabel={`${totalPassages.toLocaleString()} passages`}
              items={orderedBooks}
              opener={opener}
            />
          );
        })}
      </ul>
    </section>
  );
}

// Promulgation year for a Vatican II document (metadata.year overrides the
// document's year column when present).
function vat2Year(d: SourceDocument): number {
  const m = d.metadata?.year;
  return typeof m === "number" ? m : (d.year ?? 0);
}

function CouncilsSection({ docs, opener }: { docs: SourceDocument[]; opener: DocOpener }) {
  const meta = getCollectionMeta("councils");
  const [vat2Open, setVat2Open] = useState(false);

  // The re-ingest stores Vatican II documents with metadata.council === "Second
  // Vatican Council"; collapse them into one expandable entry.
  const vaticanIIDocs = docs.filter((d) => d.metadata?.council === "Second Vatican Council");
  const standalone = docs.filter((d) => d.metadata?.council !== "Second Vatican Council");

  // Build a unified, chronologically-sorted entry list: each standalone council
  // is a single clickable row; Vatican II is one collapsible group.
  type Entry =
    | { kind: "single"; sortYear: number; doc: SourceDocument }
    | { kind: "vatican2"; sortYear: number };

  const entries: Entry[] = standalone.map((d) => ({ kind: "single", sortYear: d.year ?? 0, doc: d }));
  if (vaticanIIDocs.length > 0) {
    const years = vaticanIIDocs.map(vat2Year).filter((y) => y > 0);
    entries.push({ kind: "vatican2", sortYear: years.length ? Math.min(...years) : 1962 });
  }
  entries.sort((a, b) => a.sortYear - b.sortYear);

  const councilCount = standalone.length + (vaticanIIDocs.length > 0 ? 1 : 0);
  const sectionPassages = docs.reduce((sum, d) => sum + d.chunk_count, 0);

  const vat2Years = vaticanIIDocs.map(vat2Year).filter((y) => y > 0);
  const vat2Range = vat2Years.length
    ? `${Math.min(...vat2Years)}–${Math.max(...vat2Years)}`
    : "";
  const vat2Passages = vaticanIIDocs.reduce((sum, d) => sum + d.chunk_count, 0);
  const vat2Sorted = [...vaticanIIDocs].sort((a, b) => vat2Year(a) - vat2Year(b));

  return (
    <section>
      <div className="flex items-center gap-3 mb-3 pb-2 border-b border-brand-surface">
        <span
          className="text-xs font-semibold px-2.5 py-0.5 rounded-full border"
          style={{ color: meta?.color, borderColor: meta?.color }}
        >
          {meta?.label ?? "councils"}
        </span>
        <span className="text-brand-muted text-xs">
          {councilCount === 1 ? "1 council" : `${councilCount} councils`}
          {" · "}
          {sectionPassages.toLocaleString()} passages
        </span>
      </div>
      <ul className="space-y-1.5">
        {entries.map((entry) => {
          if (entry.kind === "vatican2") {
            return (
              <ExpandableGroup
                key="second-vatican-council"
                open={vat2Open}
                onToggle={() => setVat2Open((v: boolean) => !v)}
                title="Second Vatican Council"
                subLabel={`${vat2Range} · ${vaticanIIDocs.length} documents`}
                rightLabel={`${vat2Passages.toLocaleString()} passages`}
                items={vat2Sorted}
                opener={opener}
              />
            );
          }
          const d = entry.doc;
          const num = d.metadata?.council_number as number | undefined;
          return (
            <li key={d.id}>
              <DocLink
                doc={d}
                opener={opener}
                className={`w-full flex items-start justify-between gap-4 px-3 py-2 rounded bg-brand-surface text-left ${LIFT}`}
              >
                <div className="min-w-0">
                  <span className="text-brand-primary text-sm">{d.title}<SourceMark doc={d} /></span>
                  <span className="text-brand-muted text-xs ml-2">
                    {num ? `#${num} · ` : ""}{d.year}
                  </span>
                </div>
                <span className="shrink-0 text-xs text-brand-muted whitespace-nowrap mt-0.5">
                  {d.chunk_count.toLocaleString()} passages
                </span>
              </DocLink>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function DocRow({ doc, opener }: { doc: SourceDocument; opener: DocOpener }) {
  const parts: string[] = [];
  if (doc.author) parts.push(doc.author);
  if (doc.year) parts.push(String(doc.year));
  const attribution = parts.join(", ");

  return (
    <li>
      <DocLink
        doc={doc}
        opener={opener}
        className={`w-full flex items-start justify-between gap-4 px-3 py-2 rounded bg-brand-surface text-left ${LIFT}`}
      >
        <div className="min-w-0">
          <span className="text-brand-primary text-sm">{doc.title}</span>
          {attribution && (
            <span className="text-brand-muted text-xs ml-2">{attribution}</span>
          )}
          {doc.translation && (
            <span className="text-brand-muted text-xs ml-1">· {doc.translation}</span>
          )}
        </div>
        <span className="shrink-0 text-xs text-brand-accent whitespace-nowrap mt-0.5">
          {excerptSourceUrl(doc) ? <ExternalLink size={12} aria-label="Opens the source in a new tab" /> : "›"}
        </span>
      </DocLink>
    </li>
  );
}

export function SourcesPage() {
  const { token, sources, sourcesLoading, sourcesReady, sourcesError, reloadSources } = useAppContext();
  const loading = sourcesLoading || !sourcesReady;
  const [query, setQuery] = useState("");
  const [collection, setCollection] = useState("all");
  const [progress, setProgress] = useState<ReadingProgress[]>([]);
  const [progressLoading, setProgressLoading] = useState(true);
  const [progressError, setProgressError] = useState(false);
  const [progressToken, setProgressToken] = useState<string | null>(null);
  const progressRequestRef = useRef(0);
  // One return key for the page's rows, stable between navigations, so each
  // href is the URL its prefetch warmed. The marker is written only for a
  // same-tab navigation; a new tab takes the reader's deep-link fallback.
  const { returnKey, markReturn } = useReaderReturnKey("library");
  const libraryHref = useCallback(
    (docId: string, chapter?: string) => readerHref({ docId, origin: "library", returnKey, chapter }),
    [returnKey],
  );
  const opener = useMemo<DocOpener>(() => ({ href: (docId) => libraryHref(docId), onNavigate: markReturn }), [libraryHref, markReturn]);

  const fetchProgress = useCallback((signal?: AbortSignal) => {
    if (!token) return Promise.resolve();
    const requestId = ++progressRequestRef.current;
    return listReadingProgress(token, 3, signal)
      .then((items) => {
        if (requestId !== progressRequestRef.current) return;
        setProgress(items);
        setProgressError(false);
        setProgressToken(token);
      })
      .catch((caught) => {
        if ((caught as DOMException).name === "AbortError" || requestId !== progressRequestRef.current) return;
        setProgressError(true);
        setProgressToken(token);
      })
      .finally(() => {
        if (!signal?.aborted && requestId === progressRequestRef.current) setProgressLoading(false);
      });
  }, [token]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchProgress(controller.signal);
    return () => {
      controller.abort();
      progressRequestRef.current += 1;
    };
  }, [fetchProgress]);

  const retryProgress = useCallback(() => {
    setProgressLoading(true);
    setProgressError(false);
    setProgressToken(null);
    void fetchProgress();
  }, [fetchProgress]);

  const visibleProgress = progressToken === token ? progress.slice(0, 3) : [];
  const visibleProgressLoading = progressToken !== token || progressLoading;
  const visibleProgressError = progressToken === token && progressError;

  const filteredSources = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return sources.filter((source) => {
      if (collection !== "all" && source.collection !== collection) return false;
      if (!term) return true;
      return [source.title, source.author, source.translation, getCollectionMeta(source.collection)?.label]
        .some((value) => value?.toLocaleLowerCase().includes(term));
    });
  }, [collection, query, sources]);
  const filteredMode = query.trim().length > 0 || collection !== "all";

  const nonBibleSources = sources.filter((s) => s.collection !== "bible");
  const totalPassages = sources.reduce((sum, s) => sum + s.chunk_count, 0);
  const totalDocuments = nonBibleSources.length + (sources.some((s) => s.collection === "bible") ? 1 : 0);

  if (loading) return <LibrarySkeleton />;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="mx-auto w-full min-w-0 max-w-3xl px-4 py-5 sm:px-6 sm:py-6">
        <h1 className="text-2xl font-semibold text-brand-primary mb-1">Library</h1>
        {!loading && !sourcesError && totalPassages > 0 && (
          <p className="text-brand-muted text-sm mb-6">
            {totalDocuments} documents · {totalPassages.toLocaleString()} total passages
          </p>
        )}
        {(loading || sourcesError || totalPassages === 0) && (
          <p className="text-brand-muted text-sm mb-6">All documents included in the search corpus.</p>
        )}

        {!loading && !sourcesError && totalPassages > 0 && (
          <div className="mb-7 space-y-3">
            <label className="flex items-center gap-2 rounded-md border border-brand-muted/30 bg-brand-surface px-3 focus-within:border-brand-accent">
              <Search size={17} className="shrink-0 text-brand-muted" aria-hidden="true" />
              <span className="sr-only">Search the Library</span>
              <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search documents, authors, or collections" className="min-w-0 flex-1 bg-transparent py-3 text-brand-primary outline-none placeholder:text-brand-muted" />
            </label>
            <label className="flex items-center gap-3 text-sm text-brand-muted">
              <span>Collection</span>
              <select value={collection} onChange={(event) => setCollection(event.target.value)} className="min-w-0 flex-1 rounded-md border border-brand-muted/30 bg-brand-surface px-3 py-2 text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
                <option value="all">All collections</option>
                {COLLECTIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
              </select>
            </label>
          </div>
        )}

        {!loading && !sourcesError && !filteredMode && (visibleProgressLoading || visibleProgress.length > 0 || visibleProgressError) && (
          <section className="mb-8" aria-labelledby="continue-reading-heading">
            <div className="mb-3 flex items-center gap-2">
              <h2 id="continue-reading-heading" className="text-base font-semibold text-brand-primary">Continue Reading</h2>
            </div>
            {visibleProgressLoading ? (
              <div className="grid min-w-0 gap-2 sm:grid-cols-2">
                {[0, 1].map((item) => <div key={item} className="h-20 animate-pulse rounded-md bg-brand-surface" />)}
              </div>
            ) : visibleProgressError ? (
              <div className="rounded-md border border-brand-muted/20 bg-brand-surface p-4">
                <p className="text-sm text-brand-muted">Your recent reading places couldn&apos;t be loaded.</p>
                <button type="button" onClick={retryProgress} className="mt-2 text-sm font-medium text-brand-accent hover:underline">Retry</button>
              </div>
            ) : (
              <div className="grid min-w-0 gap-2 sm:grid-cols-2">
                {visibleProgress.map((item) => (
                  <IntentLink key={item.document_id} href={libraryHref(item.document_id, item.chapter_key)} onNavigate={markReturn} className={`block w-full min-w-0 overflow-hidden rounded-md border border-brand-muted/20 bg-brand-surface p-3 text-left ${LIFT}`}>
                    <span className="block truncate text-sm font-medium text-brand-primary">{item.document_title}</span>
                    <span className="mt-1 block truncate text-xs text-brand-muted">{item.chapter_label}</span>
                  </IntentLink>
                ))}
              </div>
            )}
          </section>
        )}

        {!loading && sourcesError && (
          <div className="text-center py-12">
            <p className="text-brand-muted text-sm mb-4">Couldn&apos;t load the sources list. Please try again.</p>
            <button
              onClick={() => reloadSources()}
              className="px-4 py-2 rounded text-sm text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !sourcesError && totalPassages === 0 && (
          <div className="rounded-md border border-brand-muted/20 bg-brand-surface px-5 py-10 text-center">
            <p className="text-sm text-brand-primary">The Library is currently empty.</p>
            <p className="mt-2 text-sm text-brand-muted">The Library may be temporarily unavailable. Try loading it again.</p>
            <button type="button" onClick={() => reloadSources()} className="mt-4 text-sm font-medium text-brand-accent hover:underline">Try again</button>
          </div>
        )}

        {!loading && !sourcesError && filteredMode && filteredSources.length === 0 && (
          <div className="py-12 text-center">
            <p className="text-sm text-brand-muted">No Library documents match those filters.</p>
            <button type="button" onClick={() => { setQuery(""); setCollection("all"); }} className="mt-3 text-sm text-brand-accent hover:underline">Clear filters</button>
          </div>
        )}

        {!loading && !sourcesError && filteredMode && filteredSources.length > 0 && (
          <section>
            <p className="mb-3 text-xs text-brand-muted">{filteredSources.length} {filteredSources.length === 1 ? "document" : "documents"}</p>
            <ul className="space-y-1.5">
              {filteredSources.map((doc) => <DocRow key={doc.id} doc={doc} opener={opener} />)}
            </ul>
          </section>
        )}

        {!loading && !sourcesError && totalPassages > 0 && !filteredMode && (
          <div className="space-y-8">
            {COLLECTIONS.map(({ key }) => {
              const docs = sources.filter((s) => s.collection === key);
              if (docs.length === 0) return null;

              if (key === "bible") {
                return <BibleSection key={key} docs={docs} opener={opener} />;
              }

              if (key === "councils") {
                return <CouncilsSection key={key} docs={docs} opener={opener} />;
              }

              const meta = getCollectionMeta(key);
              const sectionPassages = docs.reduce((sum, d) => sum + d.chunk_count, 0);

              return (
                <section key={key}>
                  <div className="flex items-center gap-3 mb-3 pb-2 border-b border-brand-surface">
                    <span
                      className="text-xs font-semibold px-2.5 py-0.5 rounded-full border"
                      style={{ color: meta?.color, borderColor: meta?.color }}
                    >
                      {meta?.label ?? key}
                    </span>
                    <span className="text-brand-muted text-xs">
                      {docs.length === 1 ? "1 document" : `${docs.length} documents`}
                      {" · "}
                      {sectionPassages.toLocaleString()} passages
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {docs.map((doc) => (
                      <DocRow key={doc.id} doc={doc} opener={opener} />
                    ))}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
