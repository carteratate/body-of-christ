"use client";

import type { KeyboardEvent } from "react";

interface SearchBarProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  disabled: boolean;
}

export function SearchBar({
  value,
  onChange,
  onSubmit,
  loading,
  disabled,
}: SearchBarProps) {
  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !loading && !disabled) {
      onSubmit();
    }
  }

  const isDisabled = disabled || loading;
  const placeholder = disabled
    ? "Select at least one source to search."
    : "Ask a question or explore a theme…";

  return (
    <div className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={isDisabled}
        aria-label="Search query"
        className="flex-1 rounded-lg border border-brand-surface bg-brand-surface px-4 py-2.5 text-sm text-brand-primary placeholder:text-brand-muted outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:border-brand-accent transition-colors disabled:opacity-50"
      />
      <button
        onClick={() => !isDisabled && onSubmit()}
        disabled={isDisabled}
        title={disabled ? "Select at least one source to search." : undefined}
        className="flex items-center gap-2 rounded-lg bg-brand-accent px-5 py-2.5 text-sm font-semibold text-brand-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {loading ? (
          <>
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-brand-bg border-t-transparent" />
            Searching…
          </>
        ) : (
          "Search"
        )}
      </button>
    </div>
  );
}
