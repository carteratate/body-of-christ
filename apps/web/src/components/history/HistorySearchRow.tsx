"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import type { SearchSummaryV2 } from "@/lib/api";
import { trackHistoryRestored } from "@/lib/analytics";

const DELETE_REVEAL_PX = 88;
const SWIPE_THRESHOLD_PX = 44;

interface HistorySearchRowProps {
  search: SearchSummaryV2;
  active?: boolean;
  revealed: boolean;
  deleting?: boolean;
  compact?: boolean;
  origin?: "sidebar" | "history_page";
  onNavigate?: (event: React.MouseEvent<HTMLAnchorElement>) => void;
  onReveal: () => void;
  onClose: () => void;
  onDelete: () => void;
}

export function HistorySearchRow({
  search,
  active = false,
  revealed,
  deleting = false,
  compact = false,
  origin = "history_page",
  onNavigate,
  onReveal,
  onClose,
  onDelete,
}: HistorySearchRowProps) {
  const deleteButtonRef = useRef<HTMLButtonElement>(null);
  const revealButtonRef = useRef<HTMLButtonElement>(null);
  const dragStart = useRef<{ x: number; y: number; initialX: number } | null>(null);
  const dragCurrentX = useRef<number | null>(null);
  const dragged = useRef(false);
  const focusDeleteAfterReveal = useRef(false);
  const deletePointerArmed = useRef(false);
  const [dragX, setDragX] = useState<number | null>(null);

  const activeClass = "bg-brand-bg text-brand-accent border-l-2 border-brand-accent";
  const inactiveClass = "bg-brand-surface text-brand-muted hover:bg-brand-bg hover:text-brand-primary";
  const translateX = dragX ?? (revealed ? -DELETE_REVEAL_PX : 0);
  const resultLabel = search.result_count === null
    ? "Results unavailable"
    : `${search.result_count} ${search.result_count === 1 ? "result" : "results"}`;

  useEffect(() => {
    if (revealed && focusDeleteAfterReveal.current) {
      focusDeleteAfterReveal.current = false;
      deleteButtonRef.current?.focus();
    }
  }, [revealed]);

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse" || deleting) return;
    dragStart.current = {
      x: event.clientX,
      y: event.clientY,
      initialX: revealed ? -DELETE_REVEAL_PX : 0,
    };
    dragged.current = false;
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const start = dragStart.current;
    if (!start) return;
    const deltaX = event.clientX - start.x;
    const deltaY = event.clientY - start.y;
    if (Math.abs(deltaY) > Math.abs(deltaX) && !dragged.current) return;
    if (Math.abs(deltaX) > 6) dragged.current = true;
    const nextX = Math.max(-DELETE_REVEAL_PX, Math.min(0, start.initialX + deltaX));
    dragCurrentX.current = nextX;
    setDragX(nextX);
  }

  function finishPointerGesture() {
    if (!dragStart.current) return;
    const finalX = dragCurrentX.current ?? dragStart.current.initialX;
    dragStart.current = null;
    dragCurrentX.current = null;
    setDragX(null);
    if (finalX <= -SWIPE_THRESHOLD_PX) onReveal();
    else onClose();
  }

  function cancelPointerGesture() {
    dragStart.current = null;
    dragCurrentX.current = null;
    dragged.current = false;
    setDragX(null);
  }

  function closeAndRestoreFocus() {
    onClose();
    requestAnimationFrame(() => revealButtonRef.current?.focus());
  }

  function handleLinkClick(event: React.MouseEvent<HTMLAnchorElement>) {
    if (dragged.current || revealed) {
      event.preventDefault();
      event.stopPropagation();
      dragged.current = false;
      onClose();
      return;
    }
    trackHistoryRestored({ surface: origin });
    onNavigate?.(event);
  }

  return (
    <div
      data-history-row={search.id}
      className="group relative overflow-hidden rounded-md"
      onContextMenu={(event) => {
        event.preventDefault();
        if (!deleting) onReveal();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && revealed) {
          event.preventDefault();
          closeAndRestoreFocus();
        }
      }}
    >
      <div
        className={`relative z-10 flex min-w-0 items-center rounded-md transition-[transform,background-color,color] duration-200 touch-pan-y ${
          active ? activeClass : inactiveClass
        }`}
        style={{
          transform: `translateX(${translateX}px)`,
          transitionDuration: dragX === null ? undefined : "0ms",
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishPointerGesture}
        onPointerCancel={cancelPointerGesture}
      >
        <Link
          href={`/search?restore=${search.id}`}
          onClick={handleLinkClick}
          aria-label={search.query}
          className={`block min-w-0 flex-1 ${compact ? "px-2 py-1.5" : "px-3 py-3"}`}
          title={search.query}
        >
          <span className={`block truncate ${compact ? "text-xs" : "text-sm text-brand-primary"}`}>
            {search.query}
          </span>
          {!compact && (
            <span className="mt-1 block text-xs text-brand-muted">
              {resultLabel} · {new Date(search.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
            </span>
          )}
        </Link>
        <button
          ref={revealButtonRef}
          type="button"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            focusDeleteAfterReveal.current = event.detail === 0;
            onReveal();
          }}
          disabled={deleting}
          tabIndex={revealed ? -1 : 0}
          aria-label={`Show delete option for ${search.query}`}
          className={`mr-1 shrink-0 rounded p-2 text-brand-muted transition-colors hover:bg-brand-delete/15 hover:text-brand-delete focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${
            revealed ? "pointer-events-none opacity-0" : "opacity-100"
          }`}
        >
          <X size={compact ? 12 : 16} />
        </button>
      </div>

      <button
        ref={deleteButtonRef}
        type="button"
        disabled={deleting}
        tabIndex={revealed ? 0 : -1}
        aria-hidden={!revealed}
        aria-label={`Delete search: ${search.query}`}
        onPointerDown={() => {
          deletePointerArmed.current = revealed;
        }}
        onPointerCancel={() => {
          deletePointerArmed.current = false;
        }}
        onClick={(event) => {
          const isKeyboardActivation = event.detail === 0;
          const canDelete = isKeyboardActivation || deletePointerArmed.current;
          deletePointerArmed.current = false;
          if (!canDelete) {
            event.preventDefault();
            event.stopPropagation();
            return;
          }
          onDelete();
        }}
        className={`absolute inset-y-0 right-0 z-20 flex w-[88px] items-center justify-center bg-brand-delete px-3 text-sm font-semibold text-white transition-transform duration-200 hover:brightness-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white disabled:opacity-60 ${
          revealed ? "translate-x-0" : "pointer-events-none translate-x-full"
        }`}
      >
        {deleting ? "Deleting…" : "Delete"}
      </button>
    </div>
  );
}
