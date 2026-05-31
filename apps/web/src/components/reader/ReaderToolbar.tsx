"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getCollectionMeta } from "@/lib/collections";
import { type DocumentInfo, type ReaderChunk } from "@/lib/api";

interface ReaderToolbarProps {
  document: DocumentInfo;
  chunks: ReaderChunk[];
  onNavigate: (chunkId: string, direction: "prev" | "next" | "jump") => void;
}

export function ReaderToolbar({ document, chunks, onNavigate }: ReaderToolbarProps) {
  const router = useRouter();
  const [jumpValue, setJumpValue] = useState("");

  const collectionMeta = getCollectionMeta(document.collection);
  const borderColor = collectionMeta?.color ?? "var(--color-brand-accent)";

  const firstChunk = chunks[0];
  const lastChunk = chunks[chunks.length - 1];

  const isPrevDisabled = !firstChunk || firstChunk.position <= 1;
  const isNextDisabled = !lastChunk || lastChunk.position >= document.chunk_count;

  const positionInfo = chunks.length > 0
    ? `Chunks ${firstChunk.position}–${lastChunk.position} of ${document.chunk_count}`
    : `0 of ${document.chunk_count}`;

  function handlePrev() {
    if (!firstChunk || isPrevDisabled) return;
    onNavigate(firstChunk.id, "prev");
  }

  function handleNext() {
    if (!lastChunk || isNextDisabled) return;
    onNavigate(lastChunk.id, "next");
  }

  function handleJump() {
    const query = jumpValue.trim();
    if (!query) return;

    const asNumber = parseInt(query, 10);
    const matched = chunks.find((c) => {
      // Match by position if user typed a number
      if (!isNaN(asNumber) && c.position === asNumber) return true;
      // Match by reference (case-insensitive substring)
      if (c.reference && c.reference.toLowerCase().includes(query.toLowerCase())) return true;
      return false;
    });

    if (matched) {
      onNavigate(matched.id, "jump");
      setJumpValue("");
    }
  }

  function handleJumpKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      handleJump();
    }
  }

  return (
    <div className="sticky top-0 z-10 bg-brand-bg border-b border-brand-surface px-4 py-3">
      {/* Top row */}
      <div className="flex items-center gap-3 flex-wrap mb-3">
        {/* Back to results */}
        <button
          onClick={() => router.back()}
          className="text-brand-muted text-sm hover:text-brand-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          ← Results
        </button>

        <span className="text-brand-muted text-sm">·</span>

        {/* Collection badge */}
        <span
          className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium border"
          style={{ borderColor, color: borderColor }}
        >
          {collectionMeta?.label ?? document.collection}
        </span>

        {/* Document title */}
        <span className="text-sm text-brand-primary font-medium truncate max-w-xs">
          {document.title}
        </span>

        {/* Position info */}
        <span className="text-xs text-brand-muted ml-auto">
          {positionInfo}
        </span>
      </div>

      {/* Navigation row */}
      <div className="flex items-center gap-2">
        {/* Prev */}
        <button
          onClick={handlePrev}
          disabled={isPrevDisabled}
          className="px-3 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          ← Prev
        </button>

        {/* Jump input */}
        <input
          type="text"
          value={jumpValue}
          onChange={(e) => setJumpValue(e.target.value)}
          onKeyDown={handleJumpKeyDown}
          placeholder="Jump to reference…"
          className="flex-1 min-w-0 rounded bg-brand-surface border border-brand-surface text-sm text-brand-primary placeholder:text-brand-muted px-3 py-1 focus:outline-none focus:border-brand-accent transition-colors"
        />

        {/* Jump button */}
        <button
          onClick={handleJump}
          className="px-3 py-1 rounded text-xs text-brand-muted border border-brand-surface hover:text-brand-primary hover:border-brand-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          Jump
        </button>

        {/* Next */}
        <button
          onClick={handleNext}
          disabled={isNextDisabled}
          className="px-3 py-1 rounded text-xs text-brand-accent border border-brand-accent hover:bg-brand-accent hover:text-brand-bg transition-colors disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
