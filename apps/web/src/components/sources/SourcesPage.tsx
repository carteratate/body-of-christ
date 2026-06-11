"use client";

import { useCallback, useEffect, useState } from "react";
import { useAppContext } from "@/components/layout/AppShell";
import { getSources, type SourceDocument } from "@/lib/api";
import { COLLECTIONS, getCollectionMeta } from "@/lib/collections";

// Full name for Bible translation codes shown in the sources list.
const TRANSLATION_LABELS: Record<string, string> = {
  "WEB-C": "World English Bible, Catholic Edition",
};

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

function BibleSection({ docs }: { docs: SourceDocument[] }) {
  const meta = getCollectionMeta("bible");

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
          return (
            <li
              key={code}
              className="flex items-start justify-between gap-4 px-3 py-2 rounded bg-brand-surface"
            >
              <div className="min-w-0">
                <span className="text-brand-primary text-sm">{label}</span>
                <span className="text-brand-muted text-xs ml-2">
                  {books.length} books · {code}
                </span>
              </div>
              <span className="shrink-0 text-xs text-brand-muted whitespace-nowrap mt-0.5">
                {totalPassages.toLocaleString()} passages
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function CouncilsSection({ docs }: { docs: SourceDocument[] }) {
  const meta = getCollectionMeta("councils");

  // Group Vatican II documents under a single "Second Vatican Council" entry,
  // then sort everything chronologically by year.
  const vaticanIIDocs = docs.filter((d) => d.metadata?.council === "Vatican II");
  const otherDocs = docs.filter((d) => d.metadata?.council !== "Vatican II");

  const vaticanIIEntry = vaticanIIDocs.length > 0
    ? [{
        id: "vatican-ii",
        title: "Second Vatican Council",
        year: 1965,
        chunk_count: vaticanIIDocs.reduce((sum, d) => sum + d.chunk_count, 0),
        subCount: vaticanIIDocs.length,
      }]
    : [];

  const sorted = [...otherDocs.map((d) => ({ ...d, subCount: undefined })), ...vaticanIIEntry]
    .sort((a, b) => (a.year ?? 0) - (b.year ?? 0));

  const sectionPassages = docs.reduce((sum, d) => sum + d.chunk_count, 0);

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
          {sorted.length === 1 ? "1 council" : `${sorted.length} councils`}
          {" · "}
          {sectionPassages.toLocaleString()} passages
        </span>
      </div>
      <ul className="space-y-1.5">
        {sorted.map((entry) => {
          const num = (entry as SourceDocument).metadata?.council_number as number | undefined;
          return (
            <li key={entry.id} className="flex items-start justify-between gap-4 px-3 py-2 rounded bg-brand-surface">
              <div className="min-w-0">
                <span className="text-brand-primary text-sm">{entry.title}</span>
                <span className="text-brand-muted text-xs ml-2">
                  {num ? `#${num} · ` : ""}{entry.year}
                  {"subCount" in entry && entry.subCount != null
                    ? ` · ${entry.subCount} documents`
                    : ""}
                </span>
              </div>
              <span className="shrink-0 text-xs text-brand-muted whitespace-nowrap mt-0.5">
                {entry.chunk_count.toLocaleString()} passages
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function DocRow({ doc }: { doc: SourceDocument }) {
  const parts: string[] = [];
  if (doc.author) parts.push(doc.author);
  if (doc.year) parts.push(String(doc.year));
  const attribution = parts.join(", ");

  return (
    <li className="flex items-start justify-between gap-4 px-3 py-2 rounded bg-brand-surface">
      <div className="min-w-0">
        <span className="text-brand-primary text-sm">{doc.title}</span>
        {attribution && (
          <span className="text-brand-muted text-xs ml-2">{attribution}</span>
        )}
        {doc.translation && (
          <span className="text-brand-muted text-xs ml-1">· {doc.translation}</span>
        )}
      </div>
      <span className="shrink-0 text-xs text-brand-muted whitespace-nowrap mt-0.5">
        {doc.chunk_count.toLocaleString()} passages
      </span>
    </li>
  );
}

export function SourcesPage() {
  const { token, setCorpusPassages } = useAppContext();
  const [sources, setSources] = useState<SourceDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSources = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    getSources(token)
      .then((data) => {
        setSources(data);
        setCorpusPassages(data.reduce((sum, s) => sum + s.chunk_count, 0));
      })
      .catch(() => setError("Couldn't load the sources list. Please try again."))
      .finally(() => setLoading(false));
  }, [token, setCorpusPassages]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const nonBibleSources = sources.filter((s) => s.collection !== "bible");
  const totalPassages = sources.reduce((sum, s) => sum + s.chunk_count, 0);
  const totalDocuments = nonBibleSources.length + (sources.some((s) => s.collection === "bible") ? 1 : 0);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-6 max-w-3xl w-full mx-auto">
        <h1 className="text-2xl font-semibold text-brand-primary mb-1">List of Sources</h1>
        {!loading && !error && totalPassages > 0 && (
          <p className="text-brand-muted text-sm mb-6">
            {totalDocuments} documents · {totalPassages.toLocaleString()} total passages
          </p>
        )}
        {(loading || error || totalPassages === 0) && (
          <p className="text-brand-muted text-sm mb-6">All documents included in the search corpus.</p>
        )}

        {loading && <SourcesSkeleton />}

        {!loading && error && (
          <div className="text-center py-12">
            <p className="text-brand-muted text-sm mb-4">{error}</p>
            <button
              onClick={fetchSources}
              className="px-4 py-2 rounded text-sm text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !error && (
          <div className="space-y-8">
            {COLLECTIONS.map(({ key }) => {
              const docs = sources.filter((s) => s.collection === key);
              if (docs.length === 0) return null;

              if (key === "bible") {
                return <BibleSection key={key} docs={docs} />;
              }

              if (key === "councils") {
                return <CouncilsSection key={key} docs={docs} />;
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
                      <DocRow key={doc.id} doc={doc} />
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
