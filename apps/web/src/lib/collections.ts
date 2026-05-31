export interface CollectionMeta {
  key: string;
  label: string;
  color: string;
}

export const COLLECTIONS: CollectionMeta[] = [
  { key: "bible",          label: "📖 Bible",         color: "var(--color-collection-bible)" },
  { key: "catechism",      label: "⛪ Catechism",      color: "var(--color-collection-catechism)" },
  { key: "church-fathers", label: "✝ Church Fathers", color: "var(--color-collection-church-fathers)" },
  { key: "encyclicals",    label: "📜 Encyclicals",    color: "var(--color-collection-encyclicals)" },
  { key: "canon-law",      label: "⚖️ Canon Law",      color: "var(--color-collection-canon-law)" },
  { key: "saints",         label: "👼 Saints",         color: "var(--color-collection-saints)" },
];

export const ALL_COLLECTION_KEYS: string[] = COLLECTIONS.map((c) => c.key);

export function getCollectionMeta(key: string): CollectionMeta | undefined {
  return COLLECTIONS.find((c) => c.key === key);
}
