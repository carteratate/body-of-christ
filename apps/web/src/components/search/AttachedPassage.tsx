"use client";

import { useId } from "react";

import { CornerDownRight } from "lucide-react";

import type { AttachedContext } from "@/lib/api";
import { renderVerseMarkers } from "@/lib/verse-markers";

/**
 * The passage that completes a matched Summa result.
 *
 * A Summa article is a staged disputation split into one chunk per move, so a result is
 * a single move and two of them are incomplete alone:
 *
 *   answered_by — the match is an Objection, a position Aquinas REFUTES. Alone it reads
 *                 as his teaching. The attachment is his answer, and goes BELOW.
 *   answers     — the match is a Reply, his own voice, so nothing is misattributed. But
 *                 it opens mid-thought. The attachment is the objection it answers, and
 *                 goes ABOVE — so on a reply card the matched passage is second.
 *
 * Placement comes from `relation` alone, never from a label. The boundary is deliberately
 * loud: these are two different voices, and running them together as continuous prose is
 * the exact failure the feature exists to prevent. The attachment is set in a muted,
 * inset frame so the passage the user actually matched stays visually primary.
 */

function Boundary({ id, label, color, rgb }: { id: string; label: string; color: string; rgb: string }) {
  return (
    <div className="flex items-center gap-2" style={{ marginBottom: "8px" }}>
      <CornerDownRight size={11} style={{ color, flexShrink: 0 }} />
      <span
        id={id}
        // Brand text, NOT the collection colour. The collection palette is defined only
        // for the dark theme (globals.css themes --color-brand-* for light, not
        // --color-collection-*), so #55cc88 on the light background is ~1.4:1 — invisible.
        // Elsewhere that palette is decorative; here this label is the whole safety
        // mechanism, so it uses a token that is legible in both themes. The colour stays
        // on the icon and rule, which carry no meaning alone.
        className="text-brand-primary"
        style={{
          fontSize: "11px",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        {label}
      </span>
      <span
        aria-hidden
        style={{ flex: 1, height: "1px", background: `rgba(${rgb},0.25)` }}
      />
    </div>
  );
}

/**
 * The boundary text, which must state the DIRECTION as well as the voice.
 *
 * On a reply card the objection is read first, so a label that only named it would
 * reproduce the misattribution one position higher: the reader meets a position Aquinas
 * rejects with nothing yet saying he rejects it. "answered below" is what prevents that.
 */
function heading(context: AttachedContext): string {
  const label = context.parts[0]?.unit_label?.trim();
  if (context.relation === "answers") {
    return label ? `${label} — answered below` : "The objection answered below";
  }
  return "Aquinas answers this objection";
}

export function AttachedPassage({
  context,
  color,
  rgb,
}: {
  context: AttachedContext;
  color: string;
  rgb: string;
}) {
  const labelId = useId();
  // Guarded rather than trusted: `getSearchResults` casts raw JSON with no runtime
  // validation, and the whole search page sits under one ErrorBoundary — so a malformed
  // context would blank every result, not one card.
  const parts = context.parts ?? [];
  if (parts.length === 0) return null;

  return (
    <aside
      // Points at the visible label rather than repeating it: an aria-label here would
      // make a screen reader announce the direction twice on entering the region.
      aria-labelledby={labelId}
      style={{
        borderLeft: `2px solid rgba(${rgb},0.35)`,
        paddingLeft: "12px",
        // Sits away from the matched passage on the side the relation puts it.
        marginTop: context.relation === "answered_by" ? "14px" : "0",
        marginBottom: context.relation === "answers" ? "14px" : "0",
      }}
    >
      <Boundary id={labelId} label={heading(context)} color={color} rgb={rgb} />
      {parts.map((part, index) => (
        <p
          key={part.anchor ?? index}
          // Not `text-brand-muted`: at 2.52:1 on the card background this text sits far
          // under AA, and an attached determination can run several times longer than the
          // objection it answers. Dimmed enough to keep the match primary, legible enough
          // to actually read.
          className="text-sm leading-relaxed whitespace-pre-wrap text-brand-primary/75"
          style={{ marginTop: index === 0 ? 0 : "10px" }}
        >
          {renderVerseMarkers(part.content)}
        </p>
      ))}
      {context.relation === "answers" && (
        // A closing marker at the voice junction. The opening label sits at the very top
        // of the card, and an objection runs to 1,668 characters — past a phone viewport
        // — so at that scroll position, or in a screenshot of the lower half, the two
        // voices would otherwise be adjacent unlabelled prose.
        <p
          className="text-xs font-medium text-brand-primary"
          style={{ marginTop: "10px", marginBottom: "-4px" }}
        >
          ↓ Aquinas replies below
        </p>
      )}
    </aside>
  );
}
