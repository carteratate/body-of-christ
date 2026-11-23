"use client";

import { useSyncExternalStore } from "react";

/**
 * How a search result card is drawn: on its collection's tint (`tint`, the default) or
 * on the plain surface saved passages use (`plain`), keeping the collection bar.
 *
 * Saved with the account in `user_preferences.result_card_style`; this module is the
 * copy the cards read. AppShell writes the account's value here when preferences load,
 * Settings writes a change here before saving it, and a guest, who has no account, reads
 * what this browser last stored. Same shape as the theme's `theocorpus-theme`.
 */
export type ResultCardStyle = "tint" | "plain";

export const DEFAULT_RESULT_CARD_STYLE: ResultCardStyle = "tint";
export const RESULT_CARD_STYLE_KEY = "theocorpus-result-card-style";

const listeners = new Set<() => void>();
let current: ResultCardStyle | null = null;

export function parseResultCardStyle(value: unknown): ResultCardStyle {
  return value === "plain" ? "plain" : DEFAULT_RESULT_CARD_STYLE;
}

// This browser's stored style, or null when storage cannot be read.
function loadStored(): ResultCardStyle | null {
  try { return parseResultCardStyle(localStorage.getItem(RESULT_CARD_STYLE_KEY)); } catch { return null; }
}

export function readResultCardStyle(): ResultCardStyle {
  if (current === null) current = loadStored() ?? DEFAULT_RESULT_CARD_STYLE;
  return current;
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function setResultCardStyle(next: ResultCardStyle): void {
  try { localStorage.setItem(RESULT_CARD_STYLE_KEY, next); } catch {}
  if (current === next) return;
  current = next;
  notify();
}

// Another tab's change (a guest's, or one the account could not store) reaches this
// tab's cards too.
function onStorage(event: StorageEvent): void {
  if (event.key !== RESULT_CARD_STYLE_KEY && event.key !== null) return;
  // What storage holds now, not the event's value, which a newer change may have passed.
  const next = loadStored();
  if (next === null || next === current) return;
  current = next;
  notify();
}

function subscribe(listener: () => void): () => void {
  let stale = false;
  if (listeners.size === 0) {
    // Unwatched, the cache may be stale: the first card reads storage afresh, and keeps
    // the cached choice when storage cannot be read.
    const stored = loadStored();
    stale = stored !== null && current !== null && stored !== current;
    if (stored !== null) current = stored;
    window.addEventListener("storage", onStorage);
  }
  listeners.add(listener);
  if (stale) listener();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) window.removeEventListener("storage", onStorage);
  };
}

export function useResultCardStyle(): ResultCardStyle {
  return useSyncExternalStore(subscribe, readResultCardStyle, () => DEFAULT_RESULT_CARD_STYLE);
}

/** Forget the cached value (tests). */
export function resetResultCardStyleForTests(): void {
  current = null;
}
