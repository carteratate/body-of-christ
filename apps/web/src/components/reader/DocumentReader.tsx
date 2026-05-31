"use client";

import { useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { getReader, type ReaderResponse } from "@/lib/api";
import {
  trackDocumentOpened,
  trackReaderNavigation,
} from "@/lib/analytics";
import { ReaderToolbar } from "./ReaderToolbar";
import { ReaderChunk } from "./ReaderChunk";

interface DocumentReaderProps {
  docId: string;
}

function DocumentReaderInner({ docId }: DocumentReaderProps) {
  const { token } = useAppContext();
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialChunkId = searchParams.get("chunk_id");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [data, setData] = useState<ReaderResponse | null>(null);
  const [currentChunkId, setCurrentChunkId] = useState<string | null>(initialChunkId);

  const originChunkRef = useRef<HTMLDivElement | null>(null);

  // ── Initial load ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!token || !docId || !currentChunkId) return;

    setLoading(true);
    setError(null);
    setNotFound(false);

    getReader(token, docId, currentChunkId, 10)
      .then((result) => {
        setData(result);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "Failed to load document";
        if (msg.includes("404")) {
          setNotFound(true);
        } else {
          setError(msg);
        }
      })
      .finally(() => {
        setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, docId]);

  // ── Scroll origin into view after data loads ───────────────────────────────

  useEffect(() => {
    if (!data) return;
    originChunkRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [data]);

  // ── Navigation ─────────────────────────────────────────────────────────────

  async function handleNavigate(chunkId: string, direction: "next" | "prev" | "jump") {
    if (!token || !data) return;
    trackReaderNavigation({ documentId: docId, collection: data.document.collection, direction });
    trackDocumentOpened({ documentId: docId, collection: data.document.collection, source: "reader_nav" });
    setLoading(true);
    try {
      const result = await getReader(token, docId, chunkId, 10);
      setData(result);
      setCurrentChunkId(chunkId);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Navigation failed");
    } finally {
      setLoading(false);
    }
  }

  // ── Explore more ───────────────────────────────────────────────────────────

  function handleExploreMore(content: string) {
    const trimmed = content.slice(0, 200).replace(/\s+\S*$/, "");
    router.push(`/search?explore=${encodeURIComponent(trimmed)}`);
  }

  // ── Loading skeleton ───────────────────────────────────────────────────────

  if (loading && !data) {
    return (
      <div className="flex flex-col h-full bg-brand-bg">
        <div className="px-4 pt-6 space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="animate-pulse bg-brand-surface rounded h-4"
              style={{ width: `${75 + (i % 3) * 10}%` }}
            />
          ))}
        </div>
      </div>
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-brand-bg gap-4">
        <p className="text-brand-muted text-sm">This document couldn&apos;t be loaded.</p>
        <button
          onClick={() => router.back()}
          className="text-brand-accent text-sm hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          ← Back
        </button>
      </div>
    );
  }

  // ── 404 state ──────────────────────────────────────────────────────────────

  if (notFound) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-brand-bg gap-4">
        <p className="text-brand-muted text-sm">This document is no longer available.</p>
        <button
          onClick={() => router.back()}
          className="text-brand-accent text-sm hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          ← Back
        </button>
      </div>
    );
  }

  // ── Success ────────────────────────────────────────────────────────────────

  if (!data) return null;

  return (
    <div className="flex flex-col h-full bg-brand-bg">
      <ReaderToolbar
        document={data.document}
        chunks={data.chunks}
        onNavigate={handleNavigate}
      />

      <div className="flex-1 overflow-y-auto px-4 pt-4 pb-6">
        {/* Loading overlay while navigating (data already present) */}
        {loading && (
          <div className="space-y-3 mb-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="animate-pulse bg-brand-surface rounded h-4"
                style={{ width: `${75 + (i % 3) * 10}%` }}
              />
            ))}
          </div>
        )}

        {data.chunks.map((chunk) => {
          const isOrigin = chunk.id === data.highlight_chunk_id;
          return (
            <div
              key={chunk.id}
              ref={isOrigin ? originChunkRef : null}
            >
              <ReaderChunk
                chunk={chunk}
                document={data.document}
                isOrigin={isOrigin}
                token={token ?? ""}
                onExploreMore={handleExploreMore}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function DocumentReader({ docId }: DocumentReaderProps) {
  return (
    <Suspense>
      <DocumentReaderInner docId={docId} />
    </Suspense>
  );
}
