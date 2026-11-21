import { ExternalLink } from "lucide-react";
import type { HeldText } from "@/lib/api";
import { LIFT } from "@/lib/lift";

// A text of the document that is not on TheoCorpus at present (corpus cleanup 4.3).
// Never any of its text: its place, its heading, and a link that opens it online in a
// new tab, in the excerpt-only link style (issue #265).

/** A cell of the overview's section grid, the size of a chapter cell, without an ordinal. */
export function HeldCell({ held }: { held: HeldText }) {
  return (
    <a
      href={held.url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="held-text"
      className={`flex min-h-12 min-w-0 flex-col gap-1 rounded-md border border-dashed border-brand-muted/40 px-3 py-3 text-left ${LIFT}`}
    >
      <span className="min-w-0 text-sm leading-snug text-brand-muted">{held.label} · {held.heading}</span>
      <span className="text-xs text-brand-accent">
        Not on TheoCorpus at present · Read online
        <ExternalLink size={11} aria-hidden="true" className="ml-1 inline align-baseline" />
        <span className="sr-only">(opens in a new tab)</span>
      </span>
    </a>
  );
}

/** One line in the reading flow, where the text would stand. */
export function HeldLine({ held }: { held: HeldText }) {
  return (
    <a
      href={held.url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="held-text"
      className="my-4 block rounded-md border border-dashed border-brand-muted/40 px-3 py-2 text-sm leading-snug text-brand-muted transition-colors hover:border-brand-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
    >
      {held.label}: {held.heading} — not on TheoCorpus at present.{" "}
      <span className="whitespace-nowrap text-brand-accent">
        Read online
        <ExternalLink size={12} aria-hidden="true" className="ml-1 inline align-baseline" />
      </span>
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}
