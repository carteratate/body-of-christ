"use client";

import { Menu } from "lucide-react";

interface MobileTopBarProps {
  isOpen: boolean;
  onOpenMenu: () => void;
}

export function MobileTopBar({ isOpen, onOpenMenu }: MobileTopBarProps) {
  return (
    <div className="flex md:hidden items-center gap-3 h-[52px] shrink-0 px-3 border-b border-brand-surface bg-brand-surface">
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
      <span className="text-brand-accent font-semibold text-lg font-brand">TheoCorpus</span>
    </div>
  );
}
