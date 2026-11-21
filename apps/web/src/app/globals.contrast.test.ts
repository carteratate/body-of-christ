import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { COLLECTIONS } from "@/lib/collections";

// brand-muted is secondary text: it must read at WCAG's 4.5:1 on every collection card's
// tint and on the page and panel backgrounds, in both themes (CLAUDE.md §9). A card is
// tinted rgba(<collection>, 0.32) over brand-bg (ChunkCard.tsx).
const CSS = readFileSync(fileURLToPath(new URL("./globals.css", import.meta.url)), "utf8");
const CARD_TINT = 0.32;
const MINIMUM = 4.5;

function token(block: string, name: string): string {
  const match = block.match(new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`));
  if (!match) throw new Error(`no ${name} in block`);
  return match[1];
}

function rgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
}

function over(fg: [number, number, number], bg: [number, number, number], alpha: number) {
  return fg.map((v, i) => v * alpha + bg[i] * (1 - alpha)) as [number, number, number];
}

function luminance([r, g, b]: [number, number, number]): number {
  const channel = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: [number, number, number], b: [number, number, number]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const light = CSS.slice(CSS.indexOf('[data-theme="light"] {'));
const themes = { "Slate Night": CSS.slice(0, CSS.indexOf('[data-theme="light"] {')), "Ivory Vault": light };

describe.each(Object.entries(themes))("brand-muted in %s", (_, block) => {
  const muted = rgb(token(block, "brand-muted"));
  const bg = rgb(token(block, "brand-bg"));
  const surface = rgb(token(block, "brand-surface"));

  it.each(COLLECTIONS.map((c) => [c.label, c.hex] as const))(
    "reads at 4.5:1 on a %s card",
    (_label, hex) => {
      expect(contrast(muted, over(rgb(hex), bg, CARD_TINT))).toBeGreaterThanOrEqual(MINIMUM);
    },
  );

  it("reads at 4.5:1 on the page and panel backgrounds", () => {
    expect(contrast(muted, bg)).toBeGreaterThanOrEqual(MINIMUM);
    expect(contrast(muted, surface)).toBeGreaterThanOrEqual(MINIMUM);
  });
});
