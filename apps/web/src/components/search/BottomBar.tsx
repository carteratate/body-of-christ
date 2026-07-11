"use client";

import { CollectionToggles } from "./CollectionToggles";
import { QuotaControl } from "./QuotaControl";
import { SearchBar } from "./SearchBar";
import { ResultFilterBar } from "./ResultFilterBar";

interface BottomBarProps {
  // Pre-search
  activeCollections: string[];
  onToggleCollection: (c: string) => void;
  translation: string;
  onTranslationChange: (t: string) => void;
  quota: number;
  onQuotaChange: (q: number) => void;
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
  fixedQuota?: boolean;
}

export function BottomBar({
  activeCollections,
  onToggleCollection,
  translation,
  onTranslationChange,
  quota,
  onQuotaChange,
  searchValue,
  onSearchChange,
  onSearch,
  loading,
  isSearchActive,
  submittedCollections,
  visibleCollections,
  onToggleVisible,
  searchDisabled = false,
  fixedQuota = false,
}: BottomBarProps) {
  if (isSearchActive) {
    return (
      <div className="border-t border-brand-surface bg-brand-bg px-4 py-4 pb-5">
        <ResultFilterBar
          submittedCollections={submittedCollections}
          visibleCollections={visibleCollections}
          onToggleVisible={onToggleVisible}
        />
      </div>
    );
  }

  return (
    <div className="border-t border-brand-surface bg-brand-bg px-4 py-3 pb-4">
      <div className="mb-2 flex items-center justify-between gap-3 max-md:flex-col max-md:items-stretch max-md:gap-2">
        <CollectionToggles
          activeCollections={activeCollections}
          onToggle={onToggleCollection}
          translation={translation}
          onTranslationChange={onTranslationChange}
        />
        {fixedQuota ? (
          <span className="shrink-0 text-sm text-brand-muted">3 passages per source</span>
        ) : (
          <QuotaControl value={quota} onChange={onQuotaChange} />
        )}
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
