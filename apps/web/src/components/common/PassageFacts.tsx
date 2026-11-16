import { ExternalLink } from "lucide-react";
import { factNotes, formatKind, formatTranslation, type DocumentFacts } from "@/lib/attribution";
import {
  movedLine,
  readElsewhere,
  removalExplainer,
  removalHeading,
  type RedirectKind,
  type Tombstone,
} from "@/lib/corpus-lifecycle";
import type { PassageTextLabels } from "@/lib/search-stream";
import { IntentLink } from "./NavPending";
import { SourceCredit } from "./SourceLink";

const LANGUAGE_NAMES: Record<string, string> = {
  la: "Latin", el: "Greek", grc: "Greek", it: "Italian", fr: "French", de: "German",
  es: "Spanish", pt: "Portuguese", syr: "Syriac",
};

/** "Latin" for `la`; null for English or no language. */
export function languageName(code: string | null | undefined): string | null {
  if (!code || code === "en") return null;
  return LANGUAGE_NAMES[code] ?? code;
}

/** Wording approved by Carter on 12 Nov 2026 (1.2f's suggestion). */
export const SCANNED_TEXT_LABEL = "Text from a scanned edition";

/** True when the labels would render anything. */
export function hasTextLabels(labels: PassageTextLabels | null | undefined): boolean {
  return Boolean(labels?.text_source || labels?.text_status);
}

/**
 * Where the passage's text came from (corpus cleanup 2.4f): a scanned edition (1.2f),
 * or a canon's unofficial English whose Latin is official, with the Latin linked
 * (Decision log, "Canon law English and amendments (R2)"). One paragraph per label,
 * styled by the caller's block. Shown only where the passage is opened.
 */
export function TextLabels({ labels }: { labels: PassageTextLabels | null | undefined }) {
  if (!labels || !hasTextLabels(labels)) return null;
  const latin = labels.official_latin_url;
  return (
    <>
      {labels.text_source === "ocr" && <p data-testid="text-label">{SCANNED_TEXT_LABEL}</p>}
      {labels.text_status === "unofficial_english" && (
        <p data-testid="text-label">
          Unofficial English translation (L’Osservatore Romano).{" "}
          {latin ? (
            <a
              href={latin}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-accent underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
            >
              The Latin text is official<span className="sr-only"> (opens in a new tab)</span>
            </a>
          ) : "The Latin text is official"}.
        </p>
      )}
    </>
  );
}

/**
 * What an opened passage says about its text, under the text (corpus cleanup 2.4b):
 * what kind of document it is where a papal form is recorded (issue #330), the translation, then where the text came from (2.4f), then the notes, then the
 * source credit, which stays last. Shown
 * only where the passage is opened (the expanded search card, the bookmark), never
 * on a collapsed card (Decision log, "Source credits"). Renders nothing without facts
 * except the credit, so a response without them looks as it did.
 */
export function PassageFacts({ facts, passageNote, language, credit, supersededHref, textLabels }: {
  facts: DocumentFacts | null | undefined;
  passageNote?: string | null;
  language?: string | null;
  credit: string | null;
  /** The reader link for the current text, when `facts.superseded_by` names one. */
  supersededHref?: string | null;
  /** Decoded by `passageTextLabels` (2.4f). */
  textLabels?: PassageTextLabels | null;
}) {
  const kind = formatKind(facts);
  const translation = formatTranslation(facts?.translation);
  const notes = factNotes(facts, passageNote);
  const superseded = facts?.superseded_note?.trim() || null;
  const languageLabel = languageName(language);
  if (!kind && !translation && notes.length === 0 && !superseded && !languageLabel
      && !hasTextLabels(textLabels)) {
    return credit ? <SourceCredit text={credit} /> : null;
  }
  return (
    <div className="mt-3 space-y-1 text-xs leading-snug text-brand-muted" data-testid="passage-facts">
      {languageLabel && (
        <p>This passage is in {languageLabel}; it is not included in search.</p>
      )}
      {kind && <p>{kind}</p>}
      {translation && <p>{/^translat/i.test(translation) ? translation : `Translation: ${translation}`}</p>}
      <TextLabels labels={textLabels} />
      {notes.map((note) => <p key={note}>{note}</p>)}
      {superseded && (
        <p>
          {superseded}
          {supersededHref && (
            <> <IntentLink href={supersededHref} className="text-brand-accent hover:underline">Read the current text</IntentLink></>
          )}
        </p>
      )}
      {credit && <p className="pt-1">{credit}</p>}
    </div>
  );
}

/** The muted line on a saved result whose passage moved in a later publish. */
export function MovedNote({ kind }: { kind: RedirectKind | null | undefined }) {
  return <p className="mb-3 text-xs italic leading-snug text-brand-muted">{movedLine(kind)}</p>;
}

/**
 * Why a passage or document is no longer on TheoCorpus, in place of its text
 * (Carter, 9 Nov 2026: a removed passage shows no text). The heading, then the
 * registry's one sentence of reason, the Church act where there is one, and where the
 * text can still be read. The caller shows the title, author and reference.
 */
export function RemovalNotice({ tombstone, isGuest = false, className = "" }: {
  tombstone: Tombstone;
  isGuest?: boolean;
  className?: string;
}) {
  const elsewhere = readElsewhere(tombstone);
  const explainer = removalExplainer(tombstone, isGuest);
  return (
    <div className={`space-y-2 ${className}`} data-testid="removal-notice">
      <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-brand-accent">
        {removalHeading(tombstone)}
      </p>
      <p className="text-sm leading-relaxed text-brand-primary">{tombstone.public_reason}</p>
      {tombstone.church_act && (
        <p className="text-xs leading-snug text-brand-muted">Church act: {tombstone.church_act}</p>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1 text-xs">
        {elsewhere && (
          <a
            href={elsewhere.href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded border border-brand-accent px-2 py-1 text-brand-accent transition-colors hover:bg-brand-accent hover:text-brand-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            {elsewhere.label}
            <ExternalLink size={12} aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        )}
        <IntentLink href={explainer.href} className="text-brand-muted underline-offset-2 hover:text-brand-primary hover:underline">
          {explainer.label}
        </IntentLink>
      </div>
    </div>
  );
}
