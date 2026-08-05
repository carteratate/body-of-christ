"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAppContext } from "./AppShell";
import { useGuestGate } from "./guestGate";
import { Library, Bookmark, Church, Settings, BarChart3, X } from "lucide-react";
import { deleteSearch } from "@/lib/api";
import { Toast, useToast } from "@/components/common";

interface SidebarProps {
  isMobileOpen: boolean;
  onCloseMobile: () => void;
}

const DELETE_REVEAL_PX = 88;
const SWIPE_THRESHOLD_PX = 44;

interface HistorySearchRowProps {
  id: string;
  query: string;
  href: string;
  active: boolean;
  revealed: boolean;
  onNavigate: (event: React.MouseEvent) => void;
  onReveal: () => void;
  onClose: () => void;
  onDelete: (event: React.MouseEvent) => void;
}

export function HistorySearchRow({
  id,
  query,
  href,
  active,
  revealed,
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

  useEffect(() => {
    if (revealed && focusDeleteAfterReveal.current) {
      focusDeleteAfterReveal.current = false;
      deleteButtonRef.current?.focus();
    }
  }, [revealed]);

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse") return;
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

  function handleLinkClick(event: React.MouseEvent) {
    if (dragged.current || revealed) {
      event.preventDefault();
      event.stopPropagation();
      dragged.current = false;
      onClose();
      return;
    }
    onNavigate(event);
  }

  return (
    <div
      data-history-row={id}
      className="group relative overflow-hidden rounded"
      onContextMenu={(event) => {
        event.preventDefault();
        onReveal();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && revealed) {
          event.preventDefault();
          closeAndRestoreFocus();
        }
      }}
    >
      <div
        className={`relative z-10 flex min-w-0 items-center rounded transition-[transform,background-color,color] duration-200 touch-pan-y ${
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
          href={href}
          onClick={handleLinkClick}
          className="block min-w-0 flex-1 truncate px-2 py-1.5 text-xs"
          title={query}
        >
          {query}
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
          tabIndex={revealed ? -1 : 0}
          aria-label={`Show delete option for ${query}`}
          className={`shrink-0 rounded px-1.5 py-1.5 text-brand-muted transition-opacity hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary [@media(hover:none)]:sr-only [@media(hover:none)]:focus-visible:ring-0 ${
            revealed
              ? "pointer-events-none opacity-0"
              : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
          }`}
        >
          <X size={12} />
        </button>
      </div>

      <button
        ref={deleteButtonRef}
        type="button"
        tabIndex={revealed ? 0 : -1}
        aria-hidden={!revealed}
        aria-label={`Delete search: ${query}`}
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
          onDelete(event);
        }}
        className={`absolute inset-y-0 right-0 z-20 flex w-[88px] items-center justify-center bg-brand-delete px-3 text-sm font-semibold text-white transition-transform duration-200 hover:brightness-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white ${
          revealed ? "translate-x-0" : "pointer-events-none translate-x-full"
        }`}
      >
        Delete
      </button>
    </div>
  );
}

export function Sidebar({ isMobileOpen, onCloseMobile }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { newSearch, searches, pendingSearch, activeSearchId, token, removeSearch, refreshSearches } =
    useAppContext();
  const guestGate = useGuestGate();
  const { toast, showToast, dismissToast } = useToast();
  const [revealedSearchId, setRevealedSearchId] = useState<string | null>(null);

  useEffect(() => {
    if (!revealedSearchId) return;
    function closeWhenClickingElsewhere(event: PointerEvent) {
      const row = (event.target as Element | null)?.closest?.("[data-history-row]");
      if (row?.getAttribute("data-history-row") !== revealedSearchId) {
        setRevealedSearchId(null);
      }
    }
    document.addEventListener("pointerdown", closeWhenClickingElsewhere);
    return () => document.removeEventListener("pointerdown", closeWhenClickingElsewhere);
  }, [revealedSearchId]);

  function handleNewSearch() {
    // Guest funnel: New Search prompts signup instead of starting another search.
    if (guestGate) {
      guestGate.requestSignup();
      return;
    }
    router.push("/search");
    newSearch();
    setRevealedSearchId(null);
    onCloseMobile();
  }

  // Guest funnel: nav links lead to gated areas, so they prompt signup instead.
  function handleNavClick(e: React.MouseEvent) {
    if (guestGate) {
      e.preventDefault();
      guestGate.requestSignup();
      return;
    }
    setRevealedSearchId(null);
    onCloseMobile();
  }

  async function handleDeleteSearch(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    if (!token) return;
    setRevealedSearchId(null);
    removeSearch(id);
    if (id === activeSearchId) {
      router.push("/search");
      newSearch();
    }
    try {
      await deleteSearch(token, id);
      showToast("Search deleted.", "success");
    } catch {
      refreshSearches();
      showToast("Couldn't delete search. Restored.", "error");
    }
  }

  const activeClass = "bg-brand-bg text-brand-accent border-l-2 border-brand-accent";
  const inactiveClass = "text-brand-muted hover:bg-brand-bg hover:text-brand-primary";

  return (
    <>
    <aside
      id="mobile-nav-drawer"
      className={`flex flex-col w-56 shrink-0 bg-brand-surface border-r border-brand-surface h-full max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:w-72 max-md:transition-transform max-md:duration-200 ${
        isMobileOpen ? "max-md:translate-x-0" : "max-md:-translate-x-full"
      }`}
    >
      {/* App name */}
      <div className="px-4 pt-3 pb-2 border-b border-brand-bg">
        <span className="text-brand-accent font-semibold text-2xl whitespace-nowrap font-brand">TheoCorpus</span>
      </div>

      {/* New search button */}
      <div className="px-3 pt-2">
        <button
          onClick={handleNewSearch}
          className="block w-full text-center bg-brand-accent text-brand-bg rounded-md py-1.5 text-base font-semibold hover:opacity-90 transition-opacity whitespace-nowrap font-brand"
        >
          + New Search
        </button>
      </div>

      {/* Recent searches */}
      <div className="flex-1 overflow-y-auto px-3 pt-3 space-y-1">
        <p className="text-brand-muted text-[10px] uppercase tracking-widest font-medium px-1 mb-2">
          Recent
        </p>

        {/* Pending slot — shown only during a fresh/active search, never navigable */}
        {pendingSearch && (
          <div
            className={`block px-2 py-1.5 rounded text-xs truncate ${
              pendingSearch.id === activeSearchId ? activeClass : inactiveClass
            }`}
            title={pendingSearch.query}
          >
            {pendingSearch.query}
          </div>
        )}

        {/* Real DB-backed searches */}
        {searches.length === 0 && !pendingSearch && (
          <p className="text-brand-muted text-xs px-1">No recent searches.</p>
        )}
        {searches.map((s) => (
          <HistorySearchRow
            key={s.id}
            id={s.id}
            query={s.query}
            href={`/search?restore=${s.id}`}
            active={s.id === activeSearchId}
            revealed={revealedSearchId === s.id}
            onNavigate={handleNavClick}
            onReveal={() => setRevealedSearchId(s.id)}
            onClose={() => setRevealedSearchId(null)}
            onDelete={(event) => handleDeleteSearch(event, s.id)}
          />
        ))}
      </div>

      {/* Bottom nav */}
      <div className="px-3 pb-4 pt-2 border-t border-brand-bg space-y-1 text-xs">
        <Link
          href="/sources"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/sources" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Library size={12} /> List of Sources
        </Link>
        <Link
          href="/discover"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/discover" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <BarChart3 size={12} /> Custom Source Scores
        </Link>
        <Link
          href="/bookmarks"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/bookmarks" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Bookmark size={12} /> Saved Passages
        </Link>
        <Link
          href="/about"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/about" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Church size={12} /> About
        </Link>
        <Link
          href="/settings"
          onClick={handleNavClick}
          className={`flex items-center gap-1.5 px-2 py-1.5 rounded transition-colors ${
            pathname === "/settings" ? "text-brand-accent" : "text-brand-muted hover:text-brand-primary"
          }`}
        >
          <Settings size={12} /> Settings
        </Link>
      </div>
    </aside>

    {toast.visible && <Toast message={toast.message} type={toast.type} onDismiss={dismissToast} />}
    </>
  );
}
