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

export function readResultCardStyle(): ResultCardStyle {
  if (current === null) {
    let stored: string | null = null;
    try { stored = localStorage.getItem(RESULT_CARD_STYLE_KEY); } catch {}
    current = parseResultCardStyle(stored);
  }
  return current;
}

export function setResultCardStyle(next: ResultCardStyle): void {
  try { localStorage.setItem(RESULT_CARD_STYLE_KEY, next); } catch {}
  if (current === next) return;
  current = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useResultCardStyle(): ResultCardStyle {
  return useSyncExternalStore(subscribe, readResultCardStyle, () => DEFAULT_RESULT_CARD_STYLE);
}

/** Forget the cached value (tests). */
export function resetResultCardStyleForTests(): void {
  current = null;
}
