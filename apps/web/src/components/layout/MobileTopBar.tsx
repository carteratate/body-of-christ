"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { History, Menu } from "lucide-react";
import { useAppContext } from "./AppShell";
import { trackNavigationSelected } from "@/lib/analytics";

interface MobileTopBarProps {
  isOpen: boolean;
  onOpenMenu: () => void;
}

export function MobileTopBar({ isOpen, onOpenMenu }: MobileTopBarProps) {
  const pathname = usePathname();
  const { token } = useAppContext();

  return (
    <header className="flex md:hidden items-center gap-2 h-[52px] shrink-0 px-3 border-b border-brand-bg bg-brand-surface sm:gap-3">
      <button
        id="mobile-nav-trigger"
        onClick={onOpenMenu}
        aria-label="Open menu"
        aria-expanded={isOpen}
        aria-controls="mobile-nav-drawer"
        className="p-2 -ml-1 rounded text-brand-primary hover:bg-brand-bg transition-colors"
      >
        <Menu size={20} />
      </button>
      <span className="min-w-0 flex-1 truncate font-brand text-base font-semibold text-brand-accent min-[360px]:text-lg">TheoCorpus</span>
      {pathname === "/search" && token && (
        <Link
          href="/history"
          onClick={() => trackNavigationSelected({ destination: "/history", surface: "mobile_header" })}
          aria-label="Search history"
          className="flex min-h-10 items-center gap-1.5 rounded px-1 text-sm text-brand-muted transition-colors hover:bg-brand-bg hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent min-[360px]:px-2"
        >
          <History size={18} aria-hidden="true" />
          <span className="max-[359px]:sr-only">History</span>
        </Link>
      )}
    </header>
  );
}
