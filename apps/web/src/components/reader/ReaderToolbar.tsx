"use client";

import { useRouter } from "next/navigation";
import { getCollectionMeta } from "@/lib/collections";
import { type DocumentInfo, type ReaderChunk } from "@/lib/api";

interface ReaderToolbarProps {
  document: DocumentInfo;
  chunks: ReaderChunk[];
  prevNavId: string | null;
  nextNavId: string | null;
  onNavigate: (chunkId: string, direction: "prev" | "next") => void;
}

export function ReaderToolbar({ document, chunks, prevNavId, nextNavId, onNavigate }: ReaderToolbarProps) {
  const router = useRouter();

  const collectionMeta = getCollectionMeta(document.collection);
  const borderColor = collectionMeta?.color ?? "var(--color-brand-accent)";

  const firstChunk = chunks[0];
  const lastChunk = chunks[chunks.length - 1];

  const positionInfo = chunks.length > 0
    ? `Chunks ${firstChunk.position}–${lastChunk.position} of ${document.chunk_count}`
    : `0 of ${document.chunk_count}`;

  function handlePrev() {
    if (!prevNavId) return;
    onNavigate(prevNavId, "prev");
  }

  function handleNext() {
    if (!nextNavId) return;
    onNavigate(nextNavId, "next");
  }

  return (
    <div className="sticky top-0 z-10 bg-brand-bg border-b border-brand-surface px-4 py-3">
      {/* Top row */}
      <div className="flex items-center gap-3 flex-wrap mb-3">
        <button
          onClick={() => router.back()}
          className="text-brand-muted text-sm hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          ← Results
        </button>

        <span className="text-brand-muted text-sm">·</span>

        <span
          className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border"
          style={{ borderColor, color: borderColor }}
        >
          {collectionMeta?.label ?? document.collection}
        </span>

        <span className="text-sm text-brand-primary font-medium truncate max-w-xs">
          {document.title}
        </span>

        <span className="text-xs text-brand-muted ml-auto">
          {positionInfo}
        </span>
      </div>

      {/* Navigation row */}
      <div className="flex items-center gap-2">
        <button
          onClick={handlePrev}
          disabled={!prevNavId}
          className="px-3 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          ← Prev
        </button>

        <button
          onClick={handleNext}
          disabled={!nextNavId}
          className="px-3 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
