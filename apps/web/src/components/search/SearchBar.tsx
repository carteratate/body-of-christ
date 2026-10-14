"use client";

import { useLayoutEffect, useRef, type KeyboardEvent } from "react";

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // useLayoutEffect (not useEffect) so the resize happens before paint —
  // prevents the cursor visually escaping below the textarea for one frame.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    // scrollHeight leaves out the borders, which a border-box height includes.
    el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`;
  }, [value]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter submits; Shift+Enter is swallowed (search queries don't need newlines).
    if (e.key === "Enter") {
      e.preventDefault();
      if (!loading && !disabled) onSubmit();
    }
  }

  const isDisabled = disabled || loading;
  const placeholder = disabled
    ? "Select at least one source to search."
    : "A question, a thought, a doubt: what's on your mind?";

  return (
    <div className="flex gap-2 items-end">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={isDisabled}
        maxLength={1000}
        aria-label="Search query"
        className="flex-1 rounded-lg border border-brand-surface bg-brand-surface px-4 py-2.5 text-sm text-brand-primary placeholder:text-brand-muted outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:border-brand-accent transition-colors disabled:opacity-50 resize-none overflow-hidden leading-[22px]"
      />
      <button
        onClick={() => !isDisabled && onSubmit()}
        disabled={isDisabled}
        title={disabled ? "Select at least one source to search." : undefined}
        aria-busy={loading || undefined}
        className="grid min-h-11 place-items-center rounded-lg bg-brand-accent px-5 text-lg font-semibold text-brand-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 shrink-0 whitespace-nowrap font-brand"
      >
        {/* The label keeps its place while loading so the button never changes width;
            the spinner draws over it in the same grid cell. */}
        <span aria-hidden={loading || undefined} className={`brand-caps-trim col-start-1 row-start-1 ${loading ? "invisible" : ""}`}>Search</span>
        {loading && (
          <>
            <span aria-hidden="true" className="col-start-1 row-start-1 h-4 w-4 animate-spin rounded-full border-2 border-brand-bg border-t-transparent" />
            <span className="sr-only">Searching…</span>
          </>
        )}
      </button>
    </div>
  );
}
