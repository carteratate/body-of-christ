/**
 * The notes under an opened passage (corpus cleanup 4.4, issue #407). The API sends an
 * optional `card` per passage, built from the notes a 4.4 publish stores
 * (`services/api/app/card_notes.py`):
 *
 * 1. Read with care: TheoCorpus's cautions, one sentence each, opened by their kind.
 * 2. About this text: one line, kind and form · how it survives · translator · scanned.
 * 3. Required notice: the USCCB's or the Vatican's line, verbatim, last.
 *
 * No `card` means a response from before that data, which renders today's lines (the
 * 2.4b fallback). A card with empty lists renders nothing under the text (a psalm).
 */

export type CautionKind = "incomplete" | "wording" | "authorship" | "authority";

export interface CardLink {
  label: string;
  /** An external page, opened in a new tab. */
  href?: string | null;
  /** A superseded document's current text, opened in the reader. */
  document_id?: string | null;
}

export interface CardCaution {
  kind: CautionKind;
  text: string;
  link?: CardLink | null;
}

export interface PassageCard {
  cautions: CardCaution[];
  record: string[];
  notice: string | null;
}

export interface OverviewNote {
  /** The caution kind, or null for a note that is part of the record. */
  kind: CautionKind | null;
  text: string;
}

export const CAUTION_KINDS: readonly CautionKind[] = ["incomplete", "wording", "authorship", "authority"];

/** The word that opens a caution. Shown in capitals by CSS, read as a word by a screen reader. */
export const CAUTION_LABELS: Record<CautionKind, string> = {
  incomplete: "Incomplete",
  wording: "Wording",
  authorship: "Authorship",
  authority: "Authority",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function cautionKind(value: unknown): CautionKind | null {
  return typeof value === "string" && (CAUTION_KINDS as readonly string[]).includes(value)
    ? (value as CautionKind) : null;
}

function parseLink(value: unknown): CardLink | null {
  if (!isRecord(value)) return null;
  const label = text(value.label);
  const href = text(value.href);
  const documentId = text(value.document_id);
  if (!label) return null;
  if (href && /^https?:\/\//.test(href)) return { label, href, document_id: null };
  if (documentId) return { label, href: null, document_id: documentId };
  return null;
}

/**
 * The card a payload carries, or null when it has none (a response from before 4.4) or
 * it is not an object. A malformed entry inside a card is dropped, never the card: the
 * card's presence is what selects the new rendering.
 */
export function parsePassageCard(value: unknown): PassageCard | null {
  if (!isRecord(value)) return null;
  const cautions: CardCaution[] = [];
  for (const entry of Array.isArray(value.cautions) ? value.cautions : []) {
    if (!isRecord(entry)) continue;
    const kind = cautionKind(entry.kind);
    const body = text(entry.text);
    if (!kind || !body) continue;
    cautions.push({ kind, text: body, link: parseLink(entry.link) });
  }
  const record = (Array.isArray(value.record) ? value.record : [])
    .map(text)
    .filter((item): item is string => item !== null);
  return { cautions, record, notice: text(value.notice) };
}

/** The document-wide notes an overview or Library row shows, or null for a document
 *  from before 4.4 (which shows its facts as before). */
export function parseOverviewNotes(value: unknown): OverviewNote[] | null {
  if (!Array.isArray(value)) return null;
  const notes: OverviewNote[] = [];
  for (const entry of value) {
    if (!isRecord(entry)) continue;
    const body = text(entry.text);
    if (body) notes.push({ kind: cautionKind(entry.kind), text: body });
  }
  return notes;
}

/** True when the card puts anything under the text. */
export function cardHasContent(card: PassageCard): boolean {
  return card.cautions.length > 0 || card.record.length > 0 || card.notice !== null;
}

/**
 * The text a copied passage ends with: with a card, only its required notice (rule 5:
 * the rights holder's line travels with the text, "Sourced via" does not); without
 * one, today's credit.
 */
export function copiedCredit(card: PassageCard | null, credit: string | null): string | null {
  return card ? card.notice : credit;
}

/**
 * A caution's text split around its link's label, so the label is linked in place
 * ("…Romano). [The Latin text is official.]"). A label the text does not contain is
 * appended after it.
 */
export function splitAtLink(caution: CardCaution): { before: string; label: string | null; after: string } {
  const label = caution.link?.label ?? null;
  if (!label) return { before: caution.text, label: null, after: "" };
  const at = caution.text.lastIndexOf(label);
  if (at < 0) return { before: `${caution.text} `, label, after: "" };
  return { before: caution.text.slice(0, at), label, after: caution.text.slice(at + label.length) };
}
