"use client";

import { useLayoutEffect, useRef, useSyncExternalStore, type KeyboardEvent } from "react";

// The app's phone breakpoint (Sidebar, AppShell). Below it the full hints wrap.
const NARROW_QUERY = "(max-width: 767px)";

function subscribeNarrow(onChange: () => void) {
  if (typeof window.matchMedia !== "function") return () => {};
  const media = window.matchMedia(NARROW_QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function useNarrowViewport() {
  return useSyncExternalStore(
    subscribeNarrow,
    () => typeof window.matchMedia === "function" && window.matchMedia(NARROW_QUERY).matches,
    () => false,
  );
}

/** The box's hint: one line on a phone, the full wording on wider screens. */
export function searchPlaceholder(disabled: boolean, narrow: boolean): string {
  if (disabled) return narrow ? "Select a source to search." : "Select at least one source to search.";
  return narrow ? "What's on your mind?" : "A question, a thought, a doubt: what's on your mind?";
}

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
  const placeholder = searchPlaceholder(disabled, useNarrowViewport());

  // useLayoutEffect (not useEffect) so the resize happens before paint —
  // prevents the cursor visually escaping below the textarea for one frame.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    // Safari's scrollHeight leaves out a wrapped placeholder, so an empty box is
    // measured with its hint as the value, then emptied again before paint.
    const empty = el.value === "";
    if (empty) el.value = el.placeholder;
    // scrollHeight leaves out the borders, which a border-box height includes.
    const height = el.scrollHeight + el.offsetHeight - el.clientHeight;
    if (empty) el.value = "";
    el.style.height = `${height}px`;
  }, [value, placeholder]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter submits; Shift+Enter is swallowed (search queries don't need newlines).
    if (e.key === "Enter") {
      e.preventDefault();
      if (!loading && !disabled) onSubmit();
    }
  }

  const isDisabled = disabled || loading;

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
