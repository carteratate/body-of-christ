/**
 * The passage's role in its document, when naming it prevents a misreading.
 *
 * A Summa "Objection N" is a position Aquinas states IN ORDER TO REFUTE. Ingest strips
 * that marker out of `content` and into `unit_label`, so the passage itself reads as a
 * flat assertion — "It would seem that fear causes involuntariness simply..." — with
 * nothing in the text, the citation, or the collection tag to say whose position it is.
 * Rendered or copied unmarked, it presents the opposite of his teaching as his teaching.
 *
 * The attached-passage feature fixes this for the expanded card. This covers everywhere
 * else the passage travels alone: the collapsed header, the clipboard, the accessible
 * name.
 *
 * Returns null when the role is already visible in the citation, when there is no role,
 * and for the collections whose `unit_label` is a locator rather than an argumentative
 * role ("Can. 1055 §1", "§17") — naming those adds noise without preventing anything.
 */
const ROLE_BEARING_COLLECTIONS = new Set(["summa"]);

export function displayRole(
  collection: string,
  unitLabel: string | null | undefined,
  reference: string | null,
): string | null {
  if (!unitLabel || !ROLE_BEARING_COLLECTIONS.has(collection)) return null;
  const role = unitLabel.trim();
  if (!role) return null;
  // Already in the citation the user is reading; repeating it is noise.
  if (reference && reference.includes(role)) return null;
  return role;
}
