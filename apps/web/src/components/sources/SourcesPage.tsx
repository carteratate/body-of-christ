"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { type SourceDocument } from "@/lib/api";
import { COLLECTIONS, getCollectionMeta } from "@/lib/collections";

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
  open, onToggle, title, subLabel, rightLabel, items, onOpen,
}: {
  open: boolean;
  onToggle: () => void;
  title: string;
  subLabel: string;
  rightLabel: string;
  items: { id: string; title: string }[];
  onOpen: (id: string) => void;
}) {
  return (
    <li className="rounded bg-brand-surface overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-4 px-3 py-2 text-left hover:bg-brand-surface/70 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
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
        <div className="flex flex-wrap gap-1.5 px-3 pb-3 pt-1 border-t border-brand-bg/40">
          {items.map((c) => (
            <button
              key={c.id}
              onClick={() => onOpen(c.id)}
              className="text-xs text-brand-primary bg-brand-bg/60 rounded px-2 py-1 hover:text-brand-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              {c.title}
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

function SourcesSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      {[3, 1, 18, 40, 1, 1, 4, 36].map((count, i) => (
        <div key={i} className="space-y-2">
          <div className="flex items-center gap-3 pb-2 border-b border-brand-surface">
            <div className="h-5 w-28 bg-brand-muted/20 rounded-full" />
            <div className="h-4 w-36 bg-brand-muted/20 rounded" />
          </div>
          <div className="space-y-1.5">
            {Array.from({ length: Math.min(count, 6) }).map((_, j) => (
              <div key={j} className="flex items-center justify-between px-3 py-2 rounded bg-brand-surface">
                <div
                  className="h-4 bg-brand-muted/20 rounded"
                  style={{ width: `${35 + ((j * 13 + i * 7) % 45)}%` }}
                />
                <div className="h-4 w-20 bg-brand-muted/20 rounded shrink-0 ml-4" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function BibleSection({ docs, onOpen }: { docs: SourceDocument[]; onOpen: (id: string) => void }) {
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
              items={orderedBooks.map((b) => ({ id: b.id, title: b.title }))}
              onOpen={onOpen}
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

function CouncilsSection({ docs, onOpen }: { docs: SourceDocument[]; onOpen: (id: string) => void }) {
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
                items={vat2Sorted.map((d) => ({ id: d.id, title: d.title }))}
                onOpen={onOpen}
              />
            );
          }
          const d = entry.doc;
          const num = d.metadata?.council_number as number | undefined;
          return (
            <li key={d.id}>
              <button
                onClick={() => onOpen(d.id)}
                className="w-full flex items-start justify-between gap-4 px-3 py-2 rounded bg-brand-surface text-left hover:bg-brand-surface/70 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
              >
                <div className="min-w-0">
                  <span className="text-brand-primary text-sm">{d.title}</span>
                  <span className="text-brand-muted text-xs ml-2">
                    {num ? `#${num} · ` : ""}{d.year}
                  </span>
                </div>
                <span className="shrink-0 text-xs text-brand-muted whitespace-nowrap mt-0.5">
                  {d.chunk_count.toLocaleString()} passages
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function DocRow({ doc, onOpen }: { doc: SourceDocument; onOpen: (id: string) => void }) {
  const parts: string[] = [];
  if (doc.author) parts.push(doc.author);
  if (doc.year) parts.push(String(doc.year));
  const attribution = parts.join(", ");

  return (
    <li>
      <button
        onClick={() => onOpen(doc.id)}
        className="w-full flex items-start justify-between gap-4 px-3 py-2 rounded bg-brand-surface text-left hover:bg-brand-surface/70 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
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
        <span className="shrink-0 text-xs text-brand-accent whitespace-nowrap mt-0.5">›</span>
      </button>
    </li>
  );
}

export function SourcesPage() {
  const { sources, sourcesLoading: loading, sourcesError, reloadSources } = useAppContext();
  const router = useRouter();

  const openDoc = useCallback((id: string) => {
    router.push(`/reader/${id}`);
  }, [router]);

  const nonBibleSources = sources.filter((s) => s.collection !== "bible");
  const totalPassages = sources.reduce((sum, s) => sum + s.chunk_count, 0);
  const totalDocuments = nonBibleSources.length + (sources.some((s) => s.collection === "bible") ? 1 : 0);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-6 max-w-3xl w-full mx-auto">
        <h1 className="text-2xl font-semibold text-brand-primary mb-1">List of Sources</h1>
        {!loading && !sourcesError && totalPassages > 0 && (
          <p className="text-brand-muted text-sm mb-6">
            {totalDocuments} documents · {totalPassages.toLocaleString()} total passages
          </p>
        )}
        {(loading || sourcesError || totalPassages === 0) && (
          <p className="text-brand-muted text-sm mb-6">All documents included in the search corpus.</p>
        )}

        {loading && <SourcesSkeleton />}

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

        {!loading && !sourcesError && (
          <div className="space-y-8">
            {COLLECTIONS.map(({ key }) => {
              const docs = sources.filter((s) => s.collection === key);
              if (docs.length === 0) return null;

              if (key === "bible") {
                return <BibleSection key={key} docs={docs} onOpen={openDoc} />;
              }

              if (key === "councils") {
                return <CouncilsSection key={key} docs={docs} onOpen={openDoc} />;
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
                      <DocRow key={doc.id} doc={doc} onOpen={openDoc} />
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
