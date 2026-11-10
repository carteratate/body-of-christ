/**
 * What a passage says about its own text (corpus cleanup 2.4b): who wrote it, when,
 * in which translation, how sure the attribution is, and who to credit. The API sends
 * these as optional `facts` (2.4a); every formatter here returns null or today's value
 * when they are absent, so a response without them renders as before.
 */

export type Certainty = "genuine" | "disputed" | "pseudonymous" | "anonymous";

export interface DocumentFacts {
  year?: number | null;
  date_display?: string | null;
  translation?: string | null;
  genre?: string | null;
  issuer?: string | null;
  issuer_label?: string | null;
  certainty?: Certainty | null;
  attribution_note?: string | null;
  notes?: string | null;
  source_credit?: string | null;
  superseded_by?: string | null;
  superseded_note?: string | null;
  work_title?: string | null;
}

/** One work inside a document (D6), with its own attribution. */
export interface WorkInfo {
  work_key: string;
  ordinal: number;
  title: string;
  author?: string | null;
  certainty?: Certainty | null;
  attribution_note?: string | null;
  notes?: string | null;
  date_display?: string | null;
  year?: number | null;
  genre?: string | null;
  clavis_ref?: string | null;
}

const CERTAINTIES = new Set<string>(["genuine", "disputed", "pseudonymous", "anonymous"]);

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function possessive(name: string): string {
  return `${name}'s`;
}

/**
 * The author line. The registry already writes a pseudonymous work's author as
 * "Pseudo-Justin" and an anonymous one's as "Anonymous" (3.2), so only a disputed
 * attribution needs words added. A quoted author (a Father in the Catena Aurea) wins,
 * credited as quoted in the document's author's work.
 *
 * `certainty: false` leaves the disputed note off, for a place that shows
 * `certaintyTag` beside the line instead.
 */
export function formatAttribution(
  author: string | null | undefined,
  facts?: DocumentFacts | null,
  passageAuthor?: string | null,
  options: { work?: string | null; certainty?: boolean } = {},
): string | null {
  const quoted = text(passageAuthor);
  const credited = text(author);
  if (quoted) {
    if (!credited || credited === quoted) return quoted;
    const work = text(options.work);
    return work ? `${quoted}, quoted in ${possessive(credited)} ${work}` : `${quoted}, quoted by ${credited}`;
  }
  const certainty = facts?.certainty;
  if (!credited) return certainty === "anonymous" ? "Anonymous" : null;
  if (certainty === "disputed" && options.certainty !== false) return `${credited} (authorship disputed)`;
  return credited;
}

/** The date to show: the registry's display date ("c. 397–400") over the bare year. */
export function formatDate(facts?: DocumentFacts | null, fallbackYear?: number | null): string | null {
  const display = text(facts?.date_display);
  if (display) return display;
  const year = facts?.year ?? fallbackYear;
  return typeof year === "number" && Number.isFinite(year) && year !== 0 ? String(year) : null;
}

// Full names for translation codes. A translation stored as a sentence ("Translated
// by William Harman van Allen (1909)") is shown as it is.
const TRANSLATION_LABELS: Record<string, string> = {
  "WEB-C": "World English Bible, Catholic Edition",
};

export function formatTranslation(code: string | null | undefined): string | null {
  const value = text(code);
  if (!value) return null;
  return TRANSLATION_LABELS[value] ?? value;
}

/** A short tag for an attribution that is not simply genuine, or null. */
export function certaintyTag(certainty: string | null | undefined): string | null {
  if (!certainty || certainty === "genuine" || !CERTAINTIES.has(certainty)) return null;
  return certainty;
}

/**
 * The notes shown under an opened passage, in order: how sure the attribution is,
 * the document's notes, the passage's own note. A superseded document's note is
 * returned apart, because it links to the current text.
 */
export function factNotes(facts?: DocumentFacts | null, passageNote?: string | null): string[] {
  const notes = [text(facts?.attribution_note), text(facts?.notes), text(passageNote)];
  return notes.filter((note, index): note is string => note !== null && notes.indexOf(note) === index);
}

/**
 * The credit line for an opened passage: the API's `facts.source_credit`, which
 * already carries an excerpt-only document's required notice (2.4a), or the
 * excerpt-only notice itself from a response without facts.
 */
export function sourceCreditOf(
  facts: DocumentFacts | null | undefined,
  excerptCredit: string | null,
): string | null {
  return text(facts?.source_credit) ?? excerptCredit;
}

/** "papalencyclicals.net" for a link's site, for "Read it at <site>". */
export function siteName(url: string): string | null {
  try {
    const { hostname, protocol } = new URL(url);
    if (protocol !== "https:" && protocol !== "http:") return null;
    return hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

/** Keeps only the fields a `DocumentFacts` may hold, each of the right type. A facts
 *  object the API sent malformed is dropped rather than failing the passage. */
export function parseFacts(value: unknown): DocumentFacts | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const raw = value as Record<string, unknown>;
  const facts: DocumentFacts = {};
  for (const key of [
    "date_display", "translation", "genre", "issuer", "issuer_label", "attribution_note",
    "notes", "source_credit", "superseded_by", "superseded_note", "work_title",
  ] as const) {
    if (typeof raw[key] === "string") facts[key] = raw[key] as string;
  }
  if (typeof raw.year === "number" && Number.isFinite(raw.year)) facts.year = raw.year;
  if (typeof raw.certainty === "string" && CERTAINTIES.has(raw.certainty)) {
    facts.certainty = raw.certainty as Certainty;
  }
  return facts;
}
