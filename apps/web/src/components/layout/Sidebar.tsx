"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BarChart3, Bookmark, Church, History, Library, MessageSquareText, Search, Settings } from "lucide-react";
import { trackNavigationSelected } from "@/lib/analytics";
import { clearFeedbackContext } from "@/lib/feedbackContext";
import { useAppContext } from "./AppShell";
import { useGuestGate } from "./guestGate";
import { GUEST_SEARCH_LIMIT } from "@/lib/trial";

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
  const searchParams = useSearchParams();
  const { newSearch } = useAppContext();
  const guestGate = useGuestGate();
  const [mobileViewport, setMobileViewport] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setMobileViewport(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  function handleNewSearch() {
    if (guestGate) {
      if (guestGate.searchCount >= GUEST_SEARCH_LIMIT) {
        guestGate.requestSignup("limit");
        return;
      }
      router.push(searchParams.get("preview") === "1" ? "/search/guest?preview=1" : "/search/guest");
      newSearch();
      onCloseMobile();
      return;
    }
    router.push("/search");
    newSearch();
    onCloseMobile();
  }

  function handleNavClick(event: React.MouseEvent<HTMLAnchorElement>) {
    if (guestGate) {
      event.preventDefault();
      const destination = new URL(event.currentTarget.href).pathname;
      guestGate.requestSignup(
        destination === "/sources"
          ? "library"
          : destination === "/bookmarks"
            ? "saved"
            : destination === "/history"
              ? "history"
              : "feature",
      );
      return;
    }
    const destination = new URL(event.currentTarget.href).pathname;
    if (destination === "/feedback") clearFeedbackContext();
    trackNavigationSelected({
      destination,
      surface: mobileViewport ? "mobile_drawer" : "desktop_sidebar",
    });
    onCloseMobile();
  }

  const primary = [
    { href: "/sources", label: "Library", icon: <Library size={17} /> },
    { href: "/bookmarks", label: "Saved Passages", icon: <Bookmark size={17} /> },
    { href: "/history", label: "Search History", icon: <History size={17} /> },
  ];
  const isRestoredSearch = pathname === "/search" && searchParams.has("restore");

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
                active={
                  pathname === item.href
                  || (item.href === "/sources" && pathname.startsWith("/reader/"))
                  || (item.href === "/history" && isRestoredSearch)
                }
                onClick={handleNavClick}
              />
            ))}
          </div>

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
    </>
  );
}
