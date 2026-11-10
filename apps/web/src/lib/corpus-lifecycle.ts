/**
 * Passages and documents that left the corpus or moved (corpus cleanup 2.4a, 2.4b).
 *
 * A saved result, a bookmark or a reader link can name a passage a later publish
 * retired. The API then sends `status: "removed"` with a tombstone, which says why
 * and shows no text (Carter, 9 Nov 2026), or `status: "moved"` with where it went.
 * The wording around the tombstone's own sentence lives here, in one place.
 */
import { siteName } from "./attribution";

export type PassageStatus = "current" | "moved" | "removed";

export interface Tombstone {
  entity: "document" | "passage";
  rule: string;
  reason_code: string;
  /** One plain sentence of reason, from the removal registry. */
  public_reason: string;
  /** The Church's act behind the removal, rendered "<issuer>, <act>, <year>". */
  church_act?: string | null;
  /** Where the text can still be read, for a text held back rather than excluded. */
  read_elsewhere_url?: string | null;
  retired_at: string;
  title?: string | null;
  author?: string | null;
  reference?: string | null;
}

export type RedirectKind = "moved" | "split" | "merged" | "renumbered";

export interface Redirect {
  kind: RedirectKind;
  document_id: string;
  anchor?: string | null;
  chunk_id?: string | null;
  chapter_key?: string | null;
}

/** The location a reader request named, when the API followed a redirect from it. */
export interface RedirectedFrom {
  document_id: string;
  anchor?: string | null;
  chapter_key?: string | null;
}

// Texts held back, not excluded: they return when a cleared translation is found or
// permission is granted (rule E, ADR 0001), so their notice does not say "removed".
const HELD_REASONS = new Set(["translation-in-preparation", "awaiting-permission"]);

/** The notice's heading: "Removed from TheoCorpus", or "Not available on TheoCorpus"
 *  for a text that is only held back. */
export function removalHeading(tombstone: Pick<Tombstone, "reason_code">): string {
  return HELD_REASONS.has(tombstone.reason_code) ? "Not available on TheoCorpus" : "Removed from TheoCorpus";
}

/** "Read it at papalencyclicals.net", or null when the tombstone names no usable link. */
export function readElsewhere(tombstone: Pick<Tombstone, "read_elsewhere_url">): { href: string; label: string } | null {
  const href = tombstone.read_elsewhere_url;
  if (!href) return null;
  const site = siteName(href);
  return site ? { href, label: `Read it at ${site}` } : null;
}

/** The link under a notice: "Why was this removed?" to the About page, which 5.7
 *  gives a section on it, or "Why isn't this available?" for a held text. */
export function removalExplainer(tombstone: Pick<Tombstone, "reason_code">, isGuest = false): { href: string; label: string } {
  return {
    href: isGuest ? "/guest/about" : "/about",
    label: HELD_REASONS.has(tombstone.reason_code) ? "Why isn't this available?" : "Why was this removed?",
  };
}

/** The muted line on a saved result whose passage moved in a later publish. */
export function movedLine(kind: RedirectKind | null | undefined): string {
  switch (kind) {
    case "split": return "This passage was divided in a corpus update; this is where it now begins.";
    case "merged": return "This passage was joined to a neighbouring one in a corpus update.";
    case "moved": return "This passage moved to a new place in a corpus update.";
    default: return "This passage was renumbered in a corpus update.";
  }
}

export function passageStatus(value: unknown): PassageStatus {
  return value === "removed" || value === "moved" ? value : "current";
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** A tombstone from an API body, or null when it lacks the sentence it exists for. */
export function parseTombstone(value: unknown): Tombstone | null {
  if (typeof value !== "object" || value === null) return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.public_reason !== "string" || !raw.public_reason.trim()) return null;
  return {
    entity: raw.entity === "document" ? "document" : "passage",
    rule: optionalString(raw.rule) ?? "",
    reason_code: optionalString(raw.reason_code) ?? "",
    public_reason: raw.public_reason,
    church_act: optionalString(raw.church_act),
    read_elsewhere_url: optionalString(raw.read_elsewhere_url),
    retired_at: optionalString(raw.retired_at) ?? "",
    title: optionalString(raw.title),
    author: optionalString(raw.author),
    reference: optionalString(raw.reference),
  };
}

const REDIRECT_KINDS = new Set(["moved", "split", "merged", "renumbered"]);

/** A redirect from an API body, or null when it names no document to go to. */
export function parseRedirect(value: unknown): Redirect | null {
  if (typeof value !== "object" || value === null) return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.document_id !== "string" || !raw.document_id) return null;
  return {
    kind: (typeof raw.kind === "string" && REDIRECT_KINDS.has(raw.kind) ? raw.kind : "moved") as RedirectKind,
    document_id: raw.document_id,
    anchor: optionalString(raw.anchor),
    chunk_id: optionalString(raw.chunk_id),
    chapter_key: optionalString(raw.chapter_key),
  };
}

/** A result's status with the tombstone or redirect that explains it. A "removed"
 *  status with no readable tombstone, or a "moved" one with no redirect, reads as
 *  current, so the card never claims a removal it cannot explain. Absent fields stay
 *  absent, so a response without them is unchanged. */
export function parsePassageLifecycle(value: Record<string, unknown>): {
  status?: PassageStatus;
  tombstone?: Tombstone | null;
  redirect?: Redirect | null;
} {
  if (value.status === undefined && value.tombstone === undefined && value.redirect === undefined) return {};
  const tombstone = parseTombstone(value.tombstone);
  const redirect = parseRedirect(value.redirect);
  const status = passageStatus(value.status);
  return {
    status: (status === "removed" && !tombstone) || (status === "moved" && !redirect) ? "current" : status,
    tombstone,
    redirect,
  };
}
