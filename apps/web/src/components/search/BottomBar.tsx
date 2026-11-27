"use client";

import type { ScopeExclusions, SearchDraftEvent } from "@/lib/search-draft";
import { CollectionToggles } from "./CollectionToggles";
import { QuotaControl } from "./QuotaControl";
import { SearchBar } from "./SearchBar";
import { ResultFilterBar } from "./ResultFilterBar";

interface BottomBarProps {
  // Pre-search
  activeCollections: readonly string[];
  onToggleCollection: (c: string) => void;
  excluded?: Readonly<Record<string, ScopeExclusions>>;
  onScopeEvent?: (event: Extract<SearchDraftEvent, { readonly collection: string }>) => void;
  quota: number;
  onQuotaChange: (q: number) => void;
  preferenceSaveStatus?: "pending" | "saving" | "saved" | "failed" | null;
  searchValue: string;
  onSearchChange: (v: string) => void;
  onSearch: () => void;
  loading: boolean;
  // Post-search
  isSearchActive: boolean;
  submittedCollections: string[];
  visibleCollections: string[];
  onToggleVisible: (c: string) => void;
  searchDisabled?: boolean;
}

// The rule along the bar's top edge. The dividers inside the bar draw the same one,
// bleeding through the bar's padding so they span its full width as the edge does.
const BAR_RULE = "border-t border-brand-surface";

export function BottomBar({
  activeCollections,
  onToggleCollection,
  excluded,
  onScopeEvent,
  quota,
  onQuotaChange,
  preferenceSaveStatus = null,
  searchValue,
  onSearchChange,
  onSearch,
  loading,
  isSearchActive,
  submittedCollections,
  visibleCollections,
  onToggleVisible,
  searchDisabled = false,
}: BottomBarProps) {
  if (isSearchActive) {
    return (
      <div className={`shrink-0 ${BAR_RULE} bg-brand-bg px-4 py-4 pb-5 max-md:pb-[calc(1.25rem+env(safe-area-inset-bottom))]`}>
        <ResultFilterBar
          submittedCollections={submittedCollections}
          visibleCollections={visibleCollections}
          onToggleVisible={onToggleVisible}
        />
      </div>
    );
  }

  const saveStatus = preferenceSaveStatus === "failed" ? "Default not saved"
    : preferenceSaveStatus === "saved" ? "Default saved"
    : preferenceSaveStatus === "saving" ? "Saving default…" : "";

  return (
    <div className={`shrink-0 ${BAR_RULE} bg-brand-bg px-4 py-3 pb-4 max-md:pb-[calc(1rem+env(safe-area-inset-bottom))]`}>
      <CollectionToggles
        activeCollections={activeCollections}
        onToggle={onToggleCollection}
        excluded={excluded}
        onScopeEvent={onScopeEvent}
        scopesLocked={loading}
      />
      <div aria-hidden className={`-mx-4 mt-3 ${BAR_RULE}`} />
      {/* The selector alone sits on the centre line, its label hanging off its left.
          The save notice is out of the flow too, so neither moves it. */}
      <div className="relative flex justify-center py-3">
        <QuotaControl
          value={quota}
          onChange={onQuotaChange}
          focusedCollection={activeCollections.length === 1 ? activeCollections[0] : null}
        />
        <span
          role="status"
          aria-live="polite"
          className="absolute right-0 top-1/2 max-w-16 -translate-y-1/2 text-right text-[11px] leading-tight text-brand-muted md:max-w-none"
        >
          {saveStatus}
        </span>
      </div>
      <div aria-hidden className={`-mx-4 mb-3 ${BAR_RULE}`} />
      <SearchBar
        value={searchValue}
        onChange={onSearchChange}
        onSubmit={onSearch}
        loading={loading}
        disabled={activeCollections.length === 0 || searchDisabled}
      />
    </div>
  );
}
