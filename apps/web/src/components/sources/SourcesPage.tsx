"use client";

import { useCallback, useEffect, useState } from "react";
import { useAppContext } from "@/components/layout/AppShell";
import { getSources, type SourceDocument } from "@/lib/api";
import { COLLECTIONS, getCollectionMeta } from "@/lib/collections";

function SourcesSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      {[5, 1, 18, 10, 1, 1].map((count, i) => (
        <div key={i} className="space-y-2">
          <div className="flex items-center gap-3 pb-2 border-b border-brand-surface">
            <div className="h-5 w-28 bg-brand-muted/20 rounded-full" />
            <div className="h-4 w-36 bg-brand-muted/20 rounded" />
          </div>
          <div className="space-y-1.5">
            {Array.from({ length: Math.min(count, 5) }).map((_, j) => (
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
  const { token } = useAppContext();
  const [sources, setSources] = useState<SourceDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSources = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    getSources(token)
      .then((data) => setSources(data))
      .catch(() => setError("Couldn't load the sources list. Please try again."))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const totalPassages = sources.reduce((sum, s) => sum + s.chunk_count, 0);

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-6 max-w-3xl w-full mx-auto">
        <h1 className="text-2xl font-semibold text-brand-primary mb-1">List of Sources</h1>
        {!loading && !error && totalPassages > 0 && (
          <p className="text-brand-muted text-sm mb-6">
            {sources.length} documents · {totalPassages.toLocaleString()} total passages
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
