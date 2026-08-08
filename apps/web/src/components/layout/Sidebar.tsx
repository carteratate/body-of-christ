"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Bookmark, Church, History, Library, MessageSquareText, Search, Settings } from "lucide-react";
import { Toast, useToast } from "@/components/common";
import { HistorySearchRow } from "@/components/history";
import { useSearchDeletion } from "@/components/history/useSearchDeletion";
import { trackNavigationSelected } from "@/lib/analytics";
import { clearFeedbackContext } from "@/lib/feedbackContext";
import { useAppContext } from "./AppShell";
import { useGuestGate } from "./guestGate";

interface SidebarProps {
  isMobileOpen: boolean;
  onCloseMobile: () => void;
}

interface NavLinkProps {
  href: string;
  label: string;
  icon: React.ReactNode;
  active: boolean;
  onClick: (event: React.MouseEvent<HTMLAnchorElement>) => void;
}

function NavLink({ href, label, icon, active, onClick }: NavLinkProps) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={`flex min-h-10 items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${
        active
          ? "bg-brand-bg text-brand-accent"
          : "text-brand-muted hover:bg-brand-bg hover:text-brand-primary"
      }`}
    >
      {icon}
      <span>{label}</span>
    </Link>
  );
}

export function Sidebar({ isMobileOpen, onCloseMobile }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const {
    newSearch,
    searches,
    pendingSearch,
    activeSearchId,
    removeSearch,
    restoreSearch,
    refreshSearches,
    invalidateSearchHistory,
  } = useAppContext();
  const guestGate = useGuestGate();
  const { toast, showToast, dismissToast } = useToast();
  const [revealedSearchId, setRevealedSearchId] = useState<string | null>(null);
  const [mobileViewport, setMobileViewport] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setMobileViewport(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!revealedSearchId) return;
    function closeWhenClickingElsewhere(event: PointerEvent) {
      const row = (event.target as Element | null)?.closest?.("[data-history-row]");
      if (row?.getAttribute("data-history-row") !== revealedSearchId) setRevealedSearchId(null);
    }
    document.addEventListener("pointerdown", closeWhenClickingElsewhere);
    return () => document.removeEventListener("pointerdown", closeWhenClickingElsewhere);
  }, [revealedSearchId]);

  function handleNewSearch() {
    if (guestGate) {
      guestGate.requestSignup();
      return;
    }
    router.push("/search");
    newSearch();
    setRevealedSearchId(null);
    onCloseMobile();
  }

  function handleNavClick(event: React.MouseEvent<HTMLAnchorElement>) {
    if (guestGate) {
      event.preventDefault();
      guestGate.requestSignup();
      return;
    }
    const destination = new URL(event.currentTarget.href).pathname;
    if (destination === "/feedback") clearFeedbackContext();
    trackNavigationSelected({
      destination,
      surface: mobileViewport ? "mobile_drawer" : "desktop_sidebar",
    });
    setRevealedSearchId(null);
    onCloseMobile();
  }

  function removeLocally(id: string) {
    setRevealedSearchId(null);
    removeSearch(id);
  }

  const { deletingId, deleteById } = useSearchDeletion({
    searches,
    removeLocally,
    restoreLocally: restoreSearch,
    onSuccess: () => {
      refreshSearches();
      invalidateSearchHistory();
    },
    showToast,
    origin: "sidebar",
    focusAfterRemove: (index) => {
      requestAnimationFrame(() => {
        const rows = document.querySelectorAll<HTMLElement>("#sidebar-recent-searches [data-history-row] a");
        rows[Math.min(index, rows.length - 1)]?.focus();
        if (rows.length === 0) document.getElementById("sidebar-history-link")?.focus();
      });
    },
    focusAfterRestore: (id) => {
      requestAnimationFrame(() => {
        const row = Array.from(document.querySelectorAll<HTMLElement>("#sidebar-recent-searches [data-history-row]"))
          .find((item) => item.dataset.historyRow === id);
        row?.querySelector<HTMLElement>("a")?.focus();
      });
    },
  });

  const primary = [
    { href: "/sources", label: "Library", icon: <Library size={17} /> },
    { href: "/bookmarks", label: "Saved Passages", icon: <Bookmark size={17} /> },
    { href: "/history", label: "Search History", icon: <History size={17} /> },
  ];

  return (
    <>
      <aside
        id="mobile-nav-drawer"
        role={mobileViewport ? (isMobileOpen ? "dialog" : undefined) : "complementary"}
        aria-modal={mobileViewport && isMobileOpen ? true : undefined}
        aria-hidden={mobileViewport && !isMobileOpen ? true : undefined}
        inert={mobileViewport && !isMobileOpen ? true : undefined}
        aria-label={mobileViewport ? "TheoCorpus navigation" : "Primary navigation"}
        className={`flex h-full w-56 shrink-0 flex-col border-r border-brand-bg bg-brand-surface max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-40 max-md:w-72 max-md:transition-transform max-md:duration-200 ${
          isMobileOpen ? "max-md:translate-x-0" : "max-md:-translate-x-full"
        }`}
      >
        <div className="border-b border-brand-bg px-4 pb-3 pt-4">
          <span className="whitespace-nowrap font-brand text-2xl font-semibold text-brand-accent">TheoCorpus</span>
        </div>

        <div className="px-3 pt-3">
          <button
            type="button"
            onClick={handleNewSearch}
            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-brand-accent px-3 py-2 font-brand text-base font-semibold text-brand-bg transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary"
          >
            <Search size={17} aria-hidden="true" />
            New Search
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="TheoCorpus">
          <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-widest text-brand-muted">Explore</p>
          <div className="space-y-1">
            {primary.map((item) => (
              <NavLink
                key={item.href}
                {...item}
                active={pathname === item.href || (item.href === "/sources" && pathname.startsWith("/reader/"))}
                onClick={handleNavClick}
              />
            ))}
          </div>

          <section id="sidebar-recent-searches" className="mt-5 hidden md:block" aria-labelledby="recent-searches-heading">
            <div className="mb-2 flex items-center justify-between px-2">
              <p id="recent-searches-heading" className="text-[10px] font-semibold uppercase tracking-widest text-brand-muted">Recent</p>
              <Link id="sidebar-history-link" href="/history" onClick={handleNavClick} className="text-[11px] text-brand-accent hover:underline">View all</Link>
            </div>
            <div className="space-y-1">
              {pendingSearch && (
                <div className={`truncate rounded px-2 py-1.5 text-xs ${pendingSearch.id === activeSearchId ? "bg-brand-bg text-brand-accent" : "text-brand-muted"}`} title={pendingSearch.query}>
                  {pendingSearch.query}
                </div>
              )}
              {!pendingSearch && searches.length === 0 && <p className="px-2 py-1 text-xs text-brand-muted">No recent searches.</p>}
              {searches.slice(0, 5).map((search) => (
                <HistorySearchRow
                  key={search.id}
                  search={search}
                  compact
                  origin="sidebar"
                  active={search.id === activeSearchId}
                  revealed={revealedSearchId === search.id}
                  deleting={deletingId === search.id}
                  onNavigate={handleNavClick}
                  onReveal={() => setRevealedSearchId(search.id)}
                  onClose={() => setRevealedSearchId(null)}
                  onDelete={() => void deleteById(search.id)}
                />
              ))}
            </div>
          </section>

          <div className="mt-5 border-t border-brand-bg pt-4">
            <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-widest text-brand-muted">Tools</p>
            <NavLink href="/discover" label="Source Guide" icon={<BarChart3 size={17} />} active={pathname === "/discover"} onClick={handleNavClick} />
          </div>

          <div className="mt-5 border-t border-brand-bg pt-4">
            <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-widest text-brand-muted">Information</p>
            <div className="space-y-1">
              <NavLink href="/about" label="About" icon={<Church size={17} />} active={pathname === "/about"} onClick={handleNavClick} />
              <NavLink href="/feedback" label="Feedback" icon={<MessageSquareText size={17} />} active={pathname === "/feedback"} onClick={handleNavClick} />
              <NavLink href="/settings" label="Settings" icon={<Settings size={17} />} active={pathname === "/settings"} onClick={handleNavClick} />
            </div>
          </div>
        </nav>
      </aside>

      {toast.visible && <Toast message={toast.message} type={toast.type} onDismiss={dismissToast} />}
    </>
  );
}
