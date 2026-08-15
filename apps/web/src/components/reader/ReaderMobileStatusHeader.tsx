"use client";

import { Menu } from "lucide-react";
import { useAppContext } from "@/components/layout/AppShell";

export function ReaderMobileStatusHeader({ embedded = false }: { embedded?: boolean }) {
  const { mobileNavigationOpen, openMobileNavigation } = useAppContext();
  const content = (
    <>
      <button
        id="reader-app-nav-trigger"
        type="button"
        onClick={() => openMobileNavigation("reader-app-nav-trigger")}
        aria-label="Open app navigation"
        aria-controls="mobile-nav-drawer"
        aria-expanded={mobileNavigationOpen}
        className={`rounded p-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent ${embedded ? "text-brand-muted hover:bg-brand-surface hover:text-brand-primary" : "-ml-1 text-brand-primary hover:bg-brand-bg"}`}
      >
        <Menu size={embedded ? 19 : 20} aria-hidden="true" />
      </button>
      <span className="min-w-0 flex-1 truncate font-brand text-lg font-semibold text-brand-accent">TheoCorpus</span>
    </>
  );
  if (embedded) return <div className="flex min-h-10 items-center gap-1.5 md:hidden">{content}</div>;
  return <header className="flex h-[52px] shrink-0 items-center gap-2 border-b border-brand-bg bg-brand-surface px-3 md:hidden">{content}</header>;
}
