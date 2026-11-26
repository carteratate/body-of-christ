"use client";

import { useLayoutEffect, useRef, useSyncExternalStore, type KeyboardEvent } from "react";

const subscribeNever = () => () => {};

/** False in the server render and during hydration, true once the browser has the bar. */
function useHydrated() {
  return useSyncExternalStore(subscribeNever, () => true, () => false);
}

/** Size the box to its text, or to its hint when empty. */
function fitToContent(el: HTMLTextAreaElement) {
  el.style.height = "auto";
  // Safari's scrollHeight leaves out a wrapped placeholder, so an empty box is
  // measured from a hidden copy holding its hint (writing the hint into the
  // box itself would cost the user's undo history).
  let probe = el;
  if (el.value === "") {
    probe = el.cloneNode() as HTMLTextAreaElement;
    probe.value = el.placeholder;
    probe.setAttribute("aria-hidden", "true");
    probe.style.cssText = `position:absolute;visibility:hidden;width:${el.offsetWidth}px;height:auto`;
    el.after(probe);
  }
  // scrollHeight leaves out the borders, which a border-box height includes.
  const height = probe.scrollHeight + probe.offsetHeight - probe.clientHeight;
  if (probe !== el) probe.remove();
  el.style.height = `${height}px`;
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
  const hydrated = useHydrated();
  const hint = disabled
    ? "Select at least one source to search."
    : "A question, a thought, a doubt: what's on your mind?";
  // No hint in the server HTML: on a phone it wraps, and the box can't grow to fit
  // it until the layout effect below runs.
  const placeholder = hydrated ? hint : "";

  // useLayoutEffect (not useEffect) so the resize happens before paint —
  // prevents the cursor visually escaping below the textarea for one frame.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (el) fitToContent(el);
  }, [value, placeholder]);

  // Re-fit when the box's width changes (a phone rotating to portrait), since its
  // text or hint can then wrap onto another line.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el || typeof ResizeObserver !== "function") return;
    let width = el.offsetWidth;
    const observer = new ResizeObserver(() => {
      if (el.offsetWidth === width) return;
      width = el.offsetWidth;
      fitToContent(el);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

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
