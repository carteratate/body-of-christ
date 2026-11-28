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

// The rule along the bar's top edge (its border-t border-brand-surface). The phone
// dividers draw the same one, bleeding through the bar's padding to span its width.
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
      <div className="shrink-0 border-t border-brand-surface bg-brand-bg px-4 py-4 pb-5 max-md:pb-[calc(1.25rem+env(safe-area-inset-bottom))]">
        <ResultFilterBar
          submittedCollections={submittedCollections}
          visibleCollections={visibleCollections}
          onToggleVisible={onToggleVisible}
        />
      </div>
    );
  }

  return (
    <div className={`shrink-0 ${BAR_RULE} bg-brand-bg px-4 py-3 pb-4 max-md:pb-[calc(1rem+env(safe-area-inset-bottom))]`}>
      {/* Laptops: pills and selector share one row, as before. Phones: pills, a rule,
          the selector centred on its own, a rule, then the search box. */}
      <div className="mb-2 flex items-center justify-between gap-3 max-md:mb-0 max-md:flex-col max-md:items-stretch max-md:gap-0">
        <CollectionToggles
          activeCollections={activeCollections}
          onToggle={onToggleCollection}
          excluded={excluded}
          onScopeEvent={onScopeEvent}
          scopesLocked={loading}
        />
        <div aria-hidden className={`-mx-4 mt-3 md:hidden ${BAR_RULE}`} />
        {/* On phones the selector alone sits on the centre line, its label hanging off
            its left; the save notice is out of the flow too, so neither moves it. */}
        <div className="relative flex shrink-0 flex-col items-end gap-1 max-md:items-center max-md:py-3">
          <QuotaControl
            value={quota}
            onChange={onQuotaChange}
            focusedCollection={activeCollections.length === 1 ? activeCollections[0] : null}
          />
          <span
            role="status"
            aria-live="polite"
            className="min-h-4 text-[11px] text-brand-muted max-md:absolute max-md:right-0 max-md:top-1/2 max-md:min-h-0 max-md:max-w-16 max-md:-translate-y-1/2 max-md:text-right max-md:leading-tight"
          >
            {preferenceSaveStatus === "failed" ? "Default not saved"
              : preferenceSaveStatus === "saved" ? "Default saved"
              : preferenceSaveStatus === "saving" ? "Saving default…" : ""}
          </span>
        </div>
        <div aria-hidden className={`-mx-4 mb-3 md:hidden ${BAR_RULE}`} />
      </div>
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
